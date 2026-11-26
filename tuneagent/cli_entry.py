"""Console entry point for the TuneAgent interactive CLI."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    if not scripts_dir.is_dir():
        raise SystemExit(
            "找不到 scripts 目录。请从 TuneAgent 仓库目录以 editable 模式安装。"
        )
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from interactive_cli import main as interactive_main

    return interactive_main()


if __name__ == "__main__":
    raise SystemExit(main())
