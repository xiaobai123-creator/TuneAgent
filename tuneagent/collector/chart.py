"""Fetch and parse Netease public chart data for unattended collection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tuneagent.cleaning.models import Song
from tuneagent.collector.cleaning import ParsedSource

DEFAULT_CHART_URL = "https://music.163.com/api/playlist/detail"
DEFAULT_CHART_ID = 3779629  # 云音乐新歌榜
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class ChartSourceError(RuntimeError):
    """Raised when chart data cannot be fetched or parsed."""


@dataclass(frozen=True, slots=True)
class NeteaseChartSource:
    name: str = "netease-new-songs"
    chart_url: str = DEFAULT_CHART_URL
    chart_id: int = DEFAULT_CHART_ID
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not self.chart_url.startswith(("https://", "http://")):
            raise ValueError("chart_url must be an HTTP(S) URL")
        if (
            isinstance(self.chart_id, bool)
            or not isinstance(self.chart_id, int)
            or self.chart_id <= 0
        ):
            raise ValueError("chart_id must be a positive integer")
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")

    def fetch_raw(self) -> bytes:
        query = urlencode({"id": str(self.chart_id)})
        request = Request(
            f"{self.chart_url}?{query}",
            headers={
                "Accept": "application/json",
                "Referer": "https://music.163.com/",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ChartSourceError(
                        f"chart endpoint returned HTTP {response.status}"
                    )
                raw = response.read()
        except HTTPError as error:
            raise ChartSourceError(
                f"chart endpoint HTTP {error.code}: {error.reason}"
            ) from error
        except URLError as error:
            raise ChartSourceError(
                f"chart endpoint network error: {error.reason}"
            ) from error
        except TimeoutError as error:
            raise ChartSourceError(
                f"chart endpoint timed out after {self.timeout:g}s"
            ) from error

        if not raw.strip():
            raise ChartSourceError("chart endpoint returned an empty response")
        return raw

    @staticmethod
    def parse(raw: bytes) -> ParsedSource:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ChartSourceError("chart response is not valid UTF-8") from error
        except json.JSONDecodeError as error:
            raise ChartSourceError(
                f"chart response is not valid JSON: {error}"
            ) from error

        if not isinstance(payload, dict):
            raise ChartSourceError("chart response is not a JSON object")
        code = payload.get("code")
        if code not in (None, 200):
            raise ChartSourceError(f"chart response code is {code!r}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise ChartSourceError(
                "chart response does not contain a result object"
            )
        tracks = result.get("tracks")
        if not isinstance(tracks, list):
            raise ChartSourceError(
                "chart response does not contain result.tracks"
            )
        if not tracks:
            raise ChartSourceError("chart response contains no tracks")

        songs: list[Song] = []
        invalid_count = 0
        for track in tracks:
            if not isinstance(track, dict):
                invalid_count += 1
                continue
            try:
                songs.append(Song.from_netease(track))
            except ValueError:
                invalid_count += 1

        if not songs:
            raise ChartSourceError("chart response contains no valid tracks")
        return ParsedSource(songs=tuple(songs), invalid_count=invalid_count)
