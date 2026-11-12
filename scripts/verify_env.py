#!/usr/bin/env python3
"""Verify week-one dependencies, data files, and local port availability."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
AUDIO_SUFFIXES = {".mp3", ".ogg", ".wav", ".flac"}


def run_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or result.stderr.strip()


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for component in version.removeprefix("v").split("."):
        digits = "".join(character for character in component if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT_DIR / path


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.warnings = 0
        self.failed = 0

    def pass_(self, label: str, detail: str) -> None:
        self.passed += 1
        print(f"[PASS] {label}: {detail}")

    def warn(self, label: str, detail: str) -> None:
        self.warnings += 1
        print(f"[WARN] {label}: {detail}")

    def fail(self, label: str, detail: str) -> None:
        self.failed += 1
        print(f"[FAIL] {label}: {detail}")


def check_python(checker: Checker) -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        checker.pass_("Python", f"{version} (requires >=3.10)")
    else:
        checker.fail("Python", f"{version}; requires >=3.10")


def check_node(checker: Checker) -> None:
    node_path = shutil.which("node")
    if not node_path:
        checker.fail("Node.js", "node executable not found; requires >=22")
        return

    version = run_version([node_path, "--version"])
    if not version:
        checker.fail("Node.js", "unable to read node version")
        return
    if version_tuple(version) >= (22,):
        checker.pass_("Node.js", f"{version} (requires >=22)")
    else:
        checker.fail("Node.js", f"{version}; requires >=22")


def check_pnpm(checker: Checker) -> None:
    pnpm_path = shutil.which("pnpm")
    if pnpm_path:
        version = run_version([pnpm_path, "--version"])
        if version:
            checker.pass_("pnpm", version)
        else:
            checker.fail("pnpm", "executable found but version check failed")
        return

    package_json = ROOT_DIR / "package.json"
    expected = "unknown"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
            expected = str(payload.get("packageManager", "unknown"))
        except (OSError, json.JSONDecodeError):
            pass

    if shutil.which("corepack"):
        checker.warn(
            "pnpm",
            f"pnpm shim not enabled; corepack is available ({expected})",
        )
    else:
        checker.fail("pnpm", f"not found; package metadata declares {expected}")


def check_config(checker: Checker, env_values: dict[str, str]) -> str:
    example_path = ROOT_DIR / ".env.example"
    if not example_path.is_file():
        checker.fail(".env.example", "file not found")
        return "."

    example_values = read_env_file(example_path)
    required_keys = {
        "TUNEAGENT_MODE",
        "NETEASE_SEARCH_URL",
        "APP_PORT",
        "DOWNLOAD_DIR",
        "FIXTURE_PATH",
    }
    missing_keys = sorted(required_keys - example_values.keys())
    if missing_keys:
        checker.fail(".env.example", f"missing keys: {', '.join(missing_keys)}")
    else:
        checker.pass_(".env.example", f"{len(required_keys)} required keys present")

    download_dir = os.getenv("DOWNLOAD_DIR") or env_values.get("DOWNLOAD_DIR")
    return download_dir or example_values.get("DOWNLOAD_DIR", "downloads")


def check_fixture(
    checker: Checker,
    env_values: dict[str, str],
) -> None:
    fixture_value = (
        os.getenv("FIXTURE_PATH")
        or env_values.get("FIXTURE_PATH")
        or read_env_file(ROOT_DIR / ".env.example").get("FIXTURE_PATH")
        or "tests/fixtures/raw_search_guofeng.json"
    )
    fixture_path = resolve_project_path(fixture_value)
    if not fixture_path.is_file():
        checker.fail("Search fixture", f"not found: {fixture_path}")
        return

    try:
        payload: Any = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        checker.fail("Search fixture", f"invalid JSON: {error}")
        return

    songs = payload.get("result", {}).get("songs") if isinstance(payload, dict) else None
    if not isinstance(songs, list):
        checker.fail("Search fixture", "missing result.songs array")
        return
    if len(songs) < 20:
        checker.fail("Search fixture", f"contains only {len(songs)} songs; expected 20")
        return
    if not all(isinstance(song, dict) for song in songs[:20]):
        checker.fail("Search fixture", "some of the first 20 songs are not objects")
        return

    checker.pass_(
        "Search fixture",
        f"{fixture_path.relative_to(ROOT_DIR)} contains {len(songs)} raw songs",
    )


def check_downloads(checker: Checker, download_dir_value: str) -> None:
    download_dir = resolve_project_path(download_dir_value)
    if not download_dir.is_dir():
        checker.fail("Downloads", f"directory not found: {download_dir}")
        return

    audio_files = sorted(
        path
        for path in download_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in AUDIO_SUFFIXES
        and path.stat().st_size > 44
    )
    if not audio_files:
        checker.fail("Downloads", f"no non-empty audio file in {download_dir}")
        return

    details = ", ".join(
        f"{path.name} ({path.stat().st_size} bytes)" for path in audio_files
    )
    checker.pass_("Downloads", details)


def check_port(
    checker: Checker,
    env_values: dict[str, str],
) -> None:
    port_value = (
        os.getenv("APP_PORT")
        or env_values.get("APP_PORT")
        or read_env_file(ROOT_DIR / ".env.example").get("APP_PORT")
        or "3000"
    )
    try:
        port = int(port_value)
    except ValueError:
        checker.fail("Port", f"APP_PORT is not an integer: {port_value}")
        return
    if not 1 <= port <= 65535:
        checker.fail("Port", f"APP_PORT is out of range: {port}")
        return

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", port))
    except OSError as error:
        checker.fail("Port", f"127.0.0.1:{port} cannot be checked: {error}")
        return
    checker.pass_("Port", f"127.0.0.1:{port} is available")


def main() -> int:
    env_path = ROOT_DIR / ".env"
    env_values = read_env_file(env_path)
    checker = Checker()

    check_python(checker)
    check_node(checker)
    check_pnpm(checker)
    download_dir = check_config(checker, env_values)
    check_fixture(checker, env_values)
    check_downloads(checker, download_dir)
    check_port(checker, env_values)

    print(
        f"\nSummary: {checker.passed} passed, "
        f"{checker.warnings} warning(s), {checker.failed} failed"
    )
    return 1 if checker.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
