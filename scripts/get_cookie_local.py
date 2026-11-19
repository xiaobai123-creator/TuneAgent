#!/usr/bin/env python3
"""Read the Netease MUSIC_U cookie from local Chrome or Edge."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NETEASE_DOMAIN = "music.163.com"
COOKIE_FILENAME = "netease_cookie.txt"


@dataclass(frozen=True, slots=True)
class BrowserCookieResult:
    music_u: str | None
    browser: str | None
    errors: tuple[str, ...] = ()


def _cookie_name(cookie: Any) -> str | None:
    if isinstance(cookie, Mapping):
        value = cookie.get("name")
    else:
        value = getattr(cookie, "name", None)
    return value if isinstance(value, str) else None


def _cookie_value(cookie: Any) -> str | None:
    if isinstance(cookie, Mapping):
        value = cookie.get("value")
    else:
        value = getattr(cookie, "value", None)
    return value if isinstance(value, str) else None


def music_u_from_cookies(cookies: Iterable[Any]) -> str | None:
    for cookie in cookies:
        if _cookie_name(cookie) != "MUSIC_U":
            continue
        value = _cookie_value(cookie)
        if value and value.strip():
            return value.strip()
    return None


def read_music_u_from_browsers(browser_cookie3_module: Any) -> BrowserCookieResult:
    errors: list[str] = []
    loaders = (
        ("Chrome", browser_cookie3_module.chrome),
        ("Edge", browser_cookie3_module.edge),
    )
    for browser_name, loader in loaders:
        try:
            cookies = loader(domain_name=NETEASE_DOMAIN)
            value = music_u_from_cookies(cookies)
        except Exception as error:
            errors.append(f"{browser_name}: {type(error).__name__}: {error}")
            continue
        if value:
            return BrowserCookieResult(
                music_u=value,
                browser=browser_name,
                errors=tuple(errors),
            )
    return BrowserCookieResult(music_u=None, browser=None, errors=tuple(errors))


def save_cookie_file(cookie_value: str, directory: Path | None = None) -> Path:
    target_dir = (directory or Path.cwd()).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / COOKIE_FILENAME
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            output.write(f"MUSIC_U={cookie_value}\n")
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            temporary.chmod(0o600)
        os.replace(temporary, target)
        if os.name == "posix":
            target.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def print_manual_fallback() -> None:
    print(
        "💡 强烈建议安装浏览器 Cookie-Editor 插件一键复制，"
        "或参阅 docs/cookie_guide.md"
    )
    print("\n如果改用浏览器 F12 手动获取：")
    print("1. 登录 https://music.163.com/")
    print("2. 按 F12 打开开发者工具")
    print("3. 打开 Application → Storage → Cookies → https://music.163.com")
    print("4. 找到 MUSIC_U，复制它的 Value")
    print("5. 在 TuneAgent CLI 输入 /login 并粘贴")


def main() -> int:
    print("请确保您已在 Chrome 或 Edge 浏览器中登录网易云，并关闭浏览器。")
    try:
        import browser_cookie3
    except ImportError:
        print("browser-cookie3 未安装。请先执行：")
        print("python -m pip install browser-cookie3")
        print(
            "💡 也可以安装浏览器 Cookie-Editor 插件，"
            "或参阅 docs/cookie_guide.md"
        )
        return 1

    result = read_music_u_from_browsers(browser_cookie3)
    if not result.music_u:
        print("未从 Chrome 或 Edge 中找到有效的 MUSIC_U Cookie。")
        for error in result.errors:
            print(f"读取失败：{error}")
        print_manual_fallback()
        return 1

    cookie_path = save_cookie_file(result.music_u, Path.cwd())
    print(f"已在 {result.browser} 中找到网易云登录 Cookie。")
    print(
        "✅ Cookie 已保存到当前目录的 "
        f"{cookie_path.name}。请将其内容复制，并在 TuneAgent CLI "
        "中使用 /login 粘贴。"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消 Cookie 获取。")
        raise SystemExit(1) from None
