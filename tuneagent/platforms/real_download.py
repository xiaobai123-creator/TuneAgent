"""Controlled Netease download support for an authenticated user account."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

DEFAULT_ACCOUNT_URL = "https://music.163.com/api/nuser/account/get"
DEFAULT_SONG_URL_ENDPOINT = (
    "https://music.163.com/weapi/song/enhance/player/url/v1"
)
DEFAULT_COOKIE_FILE = Path(".netease_cookie")
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
SUPPORTED_QUALITIES = {"standard": "mp3"}
_MUSIC_U_PATTERN = re.compile(r"^MUSIC_U\s*=", re.IGNORECASE)
ProgressCallback = Callable[[int, int | None], None]


class RealDownloadError(RuntimeError):
    """Base error for the optional real-download path."""


class MissingCredentialsError(RealDownloadError):
    """Raised when no usable Netease cookie can be found."""


class CookieExpiredError(RealDownloadError):
    """Raised when Netease does not recognize the supplied login session."""


class CookieFilePermissionError(RealDownloadError):
    """Raised when a cookie file is readable by group or other users."""


class AccessRestrictedError(RealDownloadError):
    """Raised when the account cannot access the requested audio."""


class RealDownloadDependencyError(RealDownloadError):
    """Raised when the optional real-download dependencies are unavailable."""


class DownloadValidationError(RealDownloadError):
    """Raised when a downloaded response is not a usable audio file."""


class JsonResponseLike(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def json(self) -> Any: ...

    def close(self) -> None: ...


class StreamResponseLike(JsonResponseLike, Protocol):
    def iter_content(self, chunk_size: int = 8192) -> Iterable[bytes]: ...


class EncodedClientLike(Protocol):
    headers: MutableMapping[str, str]
    cookies: Any

    def get(self, url: str, **kwargs: Any) -> StreamResponseLike: ...

    def encoded_post(
        self,
        url: str,
        data: dict[str, Any],
    ) -> JsonResponseLike: ...


@dataclass(frozen=True, slots=True)
class RealDownloadResult:
    song_id: int
    path: Path
    manifest_path: Path
    quality: str
    size_bytes: int
    sha256: str


def parse_cookie_header(raw_value: str) -> dict[str, str]:
    """Parse a full Cookie header or a bare MUSIC_U value."""
    value = raw_value.strip()
    if not value:
        raise MissingCredentialsError("网易云 Cookie 不能为空")
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()

    if ";" not in value and not _MUSIC_U_PATTERN.match(value):
        return {"MUSIC_U": value}

    cookies: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, cookie_value = part.split("=", 1)
        normalized_name = name.strip()
        normalized_value = cookie_value.strip()
        if normalized_name and normalized_value:
            cookies[normalized_name] = normalized_value
    if not cookies.get("MUSIC_U"):
        raise MissingCredentialsError("Cookie 中缺少有效的 MUSIC_U")
    return cookies


def _read_cookie_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise MissingCredentialsError(f"Cookie 文件不存在：{path}")

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CookieFilePermissionError(
            f"Cookie 文件权限不安全：{path}；请执行 chmod 600 {path}"
        )
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise MissingCredentialsError(f"无法读取 Cookie 文件：{path}") from error
    return parse_cookie_header(content)


def load_netease_cookies(
    cookie_file: str | Path | None = None,
) -> dict[str, str]:
    """Load cookies from environment first, then from a protected file."""
    full_cookie = os.getenv("NETEASE_COOKIE", "").strip()
    if full_cookie:
        return parse_cookie_header(full_cookie)

    music_u = os.getenv("NETEASE_MUSIC_U", "").strip()
    if music_u:
        return {"MUSIC_U": music_u}

    configured_path = cookie_file or os.getenv(
        "NETEASE_COOKIE_FILE",
        str(DEFAULT_COOKIE_FILE),
    )
    return _read_cookie_file(Path(configured_path).expanduser())


def _create_encode_session(
    cookies: Mapping[str, str],
    timeout: float,
) -> EncodedClientLike:
    try:
        from netease_encode_api import EncodeSession
    except ImportError as error:
        raise RealDownloadDependencyError(
            "真实下载依赖未安装，请执行 python -m pip install -e '.[real]'"
        ) from error

    class TimeoutEncodeSession(EncodeSession):
        def request(self, method: str, url: str, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", timeout)
            return super().request(method, url, **kwargs)

    session = TimeoutEncodeSession()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://music.163.com/",
            "Origin": "https://music.163.com",
        }
    )
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".music.163.com", path="/")
    return session  # type: ignore[return-value]


def _response_json(
    response: JsonResponseLike,
    *,
    stage: str,
) -> Any:
    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise RealDownloadError(f"{stage}返回了无效 JSON") from error
    finally:
        response.close()
    if not isinstance(payload, dict):
        raise RealDownloadError(f"{stage}返回了非对象 JSON")
    return payload


def _is_audio_payload(data: bytes) -> bool:
    return (
        data.startswith((b"ID3", b"fLaC", b"OggS", b"RIFF"))
        or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
        or (len(data) >= 12 and data[4:8] == b"ftyp")
    )


class RealNeteaseDownloader:
    """Download one account-authorized standard-quality MP3."""

    def __init__(
        self,
        *,
        client: EncodedClientLike | None = None,
        cookies: Mapping[str, str] | None = None,
        cookie_file: str | Path | None = None,
        timeout: float | None = None,
        max_download_bytes: int | None = None,
    ) -> None:
        self.timeout = timeout or float(
            os.getenv("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.max_download_bytes = max_download_bytes or int(
            os.getenv(
                "NETEASE_MAX_DOWNLOAD_BYTES",
                DEFAULT_MAX_DOWNLOAD_BYTES,
            )
        )
        if self.timeout <= 0:
            raise ValueError("HTTP timeout must be greater than zero")
        if self.max_download_bytes <= 0:
            raise ValueError("maximum download size must be greater than zero")

        if client is not None:
            self.client = client
        else:
            cookie_map = dict(cookies) if cookies else load_netease_cookies(cookie_file)
            if not cookie_map.get("MUSIC_U"):
                raise MissingCredentialsError("网易云凭证中缺少 MUSIC_U")
            self.client = _create_encode_session(cookie_map, self.timeout)

    def _ensure_logged_in(self) -> None:
        try:
            response = self.client.get(DEFAULT_ACCOUNT_URL, timeout=self.timeout)
        except OSError as error:
            raise RealDownloadError(
                f"无法连接网易云账号状态接口：{error}"
            ) from error
        if response.status_code in {401, 403}:
            response.close()
            raise CookieExpiredError("网易云 Cookie 已过期，请重新获取 MUSIC_U")
        if response.status_code != 200:
            response.close()
            raise CookieExpiredError(
                f"无法确认网易云登录状态：HTTP {response.status_code}"
            )
        payload = _response_json(response, stage="账号状态接口")
        if payload.get("code") != 200 or not payload.get("account"):
            raise CookieExpiredError("网易云 Cookie 已失效或账号未登录")

    def check_login(self) -> None:
        """Validate the configured cookie without downloading any audio."""
        self._ensure_logged_in()

    def _resolve_audio_url(self, song_id: int) -> str:
        try:
            response = self.client.encoded_post(
                DEFAULT_SONG_URL_ENDPOINT,
                {
                    "ids": json.dumps([song_id]),
                    "level": "standard",
                    "encodeType": "mp3",
                },
            )
        except OSError as error:
            raise RealDownloadError(f"无法请求网易云歌曲地址：{error}") from error
        if response.status_code in {401, 403}:
            response.close()
            raise CookieExpiredError("网易云登录状态已失效")
        if response.status_code != 200:
            response.close()
            raise RealDownloadError(
                f"获取歌曲地址失败：HTTP {response.status_code}"
            )

        payload = _response_json(response, stage="歌曲地址接口")
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise AccessRestrictedError(f"歌曲 {song_id} 没有可用的下载数据")

        item = data[0]
        audio_url = item.get("url")
        if not isinstance(audio_url, str) or not audio_url.startswith(
            ("https://", "http://")
        ):
            code = item.get("code", payload.get("code", "unknown"))
            fee = item.get("fee", "unknown")
            raise AccessRestrictedError(
                f"歌曲 {song_id} 无可用地址，可能受 VIP、地区或版权限制"
                f"（code={code}, fee={fee}）"
            )
        return audio_url

    def download(
        self,
        song_id: int,
        dest_dir: str | Path,
        *,
        quality: str = "standard",
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> RealDownloadResult:
        if isinstance(song_id, bool) or not isinstance(song_id, int) or song_id <= 0:
            raise ValueError("song_id must be a positive integer")
        if quality not in SUPPORTED_QUALITIES:
            raise ValueError(
                f"unsupported quality {quality!r}; only standard MP3 is enabled"
            )

        self._ensure_logged_in()
        audio_url = self._resolve_audio_url(song_id)
        destination = Path(dest_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"netease-{song_id}-{quality}.mp3"
        if target.exists() and not overwrite:
            raise RealDownloadError(
                f"目标文件已存在：{target}；如需覆盖请使用 --overwrite"
            )

        partial_path = target.with_suffix(".mp3.part")
        manifest_path = target.with_suffix(".mp3.json")
        digest = hashlib.sha256()
        total_bytes = 0
        first_bytes = b""
        total_to_download: int | None = None
        try:
            response = self.client.get(
                audio_url,
                stream=True,
                timeout=self.timeout,
            )
        except OSError as error:
            # Do not include the audio URL in the error: it may contain a
            # short-lived account token.
            raise RealDownloadError(
                "无法连接音频地址，网络错误或地址已过期"
            ) from error

        try:
            if response.status_code in {401, 403}:
                raise AccessRestrictedError(
                    "音频地址拒绝访问，账号权限可能已失效"
                )
            if response.status_code != 200:
                raise RealDownloadError(
                    f"下载音频失败：HTTP {response.status_code}"
                )

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > self.max_download_bytes:
                    raise DownloadValidationError("音频文件超过允许的最大大小")
                if declared_size > 0:
                    total_to_download = declared_size

            if progress_callback:
                progress_callback(0, total_to_download)

            with partial_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > self.max_download_bytes:
                        raise DownloadValidationError("音频文件超过允许的最大大小")
                    if len(first_bytes) < 16:
                        first_bytes += chunk[: 16 - len(first_bytes)]
                    digest.update(chunk)
                    output.write(chunk)
                    if progress_callback:
                        progress_callback(total_bytes, total_to_download)

            if total_bytes == 0:
                raise DownloadValidationError("下载得到空文件")
            if not _is_audio_payload(first_bytes):
                raise DownloadValidationError("下载内容不是可识别的音频格式")
            os.replace(partial_path, target)
        except OSError as error:
            raise RealDownloadError(f"保存音频失败：{error}") from error
        finally:
            response.close()
            if partial_path.exists():
                partial_path.unlink()

        sha256 = digest.hexdigest()
        manifest = {
            "song_id": song_id,
            "file": target.name,
            "quality": quality,
            "size_bytes": total_bytes,
            "sha256": sha256,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "notice": (
                "Downloaded for authorized personal study only; comply with "
                "Netease terms, copyright law, and local regulations."
            ),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return RealDownloadResult(
            song_id=song_id,
            path=target,
            manifest_path=manifest_path,
            quality=quality,
            size_bytes=total_bytes,
            sha256=sha256,
        )
