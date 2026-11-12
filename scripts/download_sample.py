#!/usr/bin/env python3
"""Download a legally reusable test audio file and record its provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
SOURCE_URL = "https://loremfile.dev/mp3/sine-440hz-3s.mp3"
SOURCE_PAGE = "https://loremfile.dev/mp3"
TEST_AUDIO_NAME = "test-tone-3s.mp3"
FALLBACK_AUDIO_NAME = "test-silence.wav"
LICENSE_NAME = "CC0 1.0 Universal"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
ATTRIBUTION = "LoremFile sample MP3"
GENERATED_LICENSE = "Locally generated; no third-party copyrighted content"
DEFAULT_TIMEOUT_SECONDS = 20
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
VALID_AUDIO_SIGNATURES = (
    b"OggS",
    b"ID3",
    b"RIFF",
    b"fLaC",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download one public test audio file into the downloads directory."
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"target directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing test audio file",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the network download and generate one second of silence",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(
            os.getenv("HTTP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        ),
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser.parse_args()


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT_DIR / path


def has_audio_signature(data: bytes) -> bool:
    return data.startswith(VALID_AUDIO_SIGNATURES)


def build_request() -> Request:
    return Request(
        SOURCE_URL,
        headers={
            "Accept": "audio/*,*/*;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    )


def download_file(target: Path, timeout: float) -> tuple[int, str]:
    temporary_path = target.with_suffix(f"{target.suffix}.part")
    digest = hashlib.sha256()
    total_bytes = 0

    try:
        with urlopen(build_request(), timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"unexpected HTTP status: {response.status}")

            with temporary_path.open("wb") as output:
                while chunk := response.read(64 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"download exceeded {MAX_DOWNLOAD_BYTES} bytes"
                        )
                    digest.update(chunk)
                    output.write(chunk)

        if total_bytes == 0:
            raise RuntimeError("downloaded file is empty")

        with temporary_path.open("rb") as downloaded:
            if not has_audio_signature(downloaded.read(16)):
                raise RuntimeError("downloaded file is not a recognized audio format")

        os.replace(temporary_path, target)
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}: {error.reason}") from error
    except URLError as error:
        raise RuntimeError(f"network error: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError(f"request timed out after {timeout:g}s") from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return total_bytes, digest.hexdigest()


def generate_silent_wav(target: Path) -> tuple[int, str]:
    sample_rate = 8_000
    sample_width = 2
    channels = 1
    silent_frames = b"\x00\x00" * sample_rate

    with wave.open(str(target), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        output.writeframes(silent_frames)

    data = target.read_bytes()
    if not data.startswith(b"RIFF"):
        raise RuntimeError("generated fallback is not a valid WAV file")
    return len(data), hashlib.sha256(data).hexdigest()


def remove_generated_fallback(download_dir: Path) -> None:
    fallback_target = download_dir / FALLBACK_AUDIO_NAME
    fallback_manifest = fallback_target.with_suffix(f"{fallback_target.suffix}.json")
    for path in (fallback_target, fallback_manifest):
        if path.exists():
            path.unlink()


def write_manifest(
    target: Path,
    size_bytes: int,
    sha256: str,
    *,
    source_kind: str,
    source_url: str | None,
    source_page: str | None,
    license_name: str,
    license_url: str | None,
    attribution: str,
) -> Path:
    manifest_path = target.with_suffix(f"{target.suffix}.json")
    manifest: dict[str, Any] = {
        "file": target.name,
        "source_kind": source_kind,
        "source_url": source_url,
        "source_page": source_page,
        "license": license_name,
        "license_url": license_url,
        "attribution": attribution,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        raise ValueError("--timeout must be greater than zero")

    download_dir = resolve_project_path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / TEST_AUDIO_NAME

    if not args.offline:
        if target.exists() and target.stat().st_size > 0 and not args.force:
            with target.open("rb") as existing:
                if not has_audio_signature(existing.read(16)):
                    raise RuntimeError(
                        f"existing file is not valid audio: {target}; use --force"
                    )
            print(f"Reusing existing test audio: {target}")
            print(f"Size: {target.stat().st_size} bytes")
            print(f"License: {LICENSE_NAME}")
            print(f"Source: {SOURCE_URL}")
            return 0

        try:
            size_bytes, sha256 = download_file(target, args.timeout)
            manifest_path = write_manifest(
                target,
                size_bytes,
                sha256,
                source_kind="downloaded",
                source_url=SOURCE_URL,
                source_page=SOURCE_PAGE,
                license_name=LICENSE_NAME,
                license_url=LICENSE_URL,
                attribution=ATTRIBUTION,
            )
            print(f"Downloaded test audio to {target}")
            print(f"Size: {size_bytes} bytes")
            print(f"SHA-256: {sha256}")
            print(f"License: {LICENSE_NAME}")
            print(f"Source: {SOURCE_URL}")
            print(f"Manifest: {manifest_path}")
            remove_generated_fallback(download_dir)
            return 0
        except RuntimeError as error:
            print(
                f"Download unavailable ({error}); generating local fallback.",
                file=sys.stderr,
            )

    fallback_target = download_dir / FALLBACK_AUDIO_NAME
    size_bytes, sha256 = generate_silent_wav(fallback_target)
    manifest_path = write_manifest(
        fallback_target,
        size_bytes,
        sha256,
        source_kind="generated",
        source_url=None,
        source_page=None,
        license_name=GENERATED_LICENSE,
        license_url=None,
        attribution="Generated locally by scripts/download_sample.py",
    )
    print(f"Generated one second of silence at {fallback_target}")
    print(f"Size: {size_bytes} bytes")
    print(f"SHA-256: {sha256}")
    print(f"License: {GENERATED_LICENSE}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"download_sample: {error}", file=sys.stderr)
        raise SystemExit(1) from error
