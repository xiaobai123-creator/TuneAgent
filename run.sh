#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_before_exit() {
  if [ -t 0 ]; then
    printf '\n按 Enter 键退出...'
    read -r _
  fi
}

fail() {
  printf '\n[错误] %s\n' "$1" >&2
  shift
  for message in "$@"; do
    printf '%s\n' "$message" >&2
  done
  pause_before_exit
  exit 1
}

find_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c \
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN="$(find_python)" || fail \
  "未检测到 Python 3.10 或更高版本。" \
  "请先安装 Python，并确认 python3 或 python 可以从终端运行。"

if [ ! -x ".venv/bin/python" ]; then
  printf '未检测到 .venv，正在创建虚拟环境...\n'
  "$PYTHON_BIN" -m venv .venv || fail \
    "创建 Python 虚拟环境失败。" \
    "Ubuntu/Debian 用户可先执行：sudo apt install python3-venv" \
    "然后重新运行：bash run.sh"
fi

if [ ! -f ".venv/bin/activate" ]; then
  fail \
    "虚拟环境不完整：缺少 .venv/bin/activate。" \
    "请删除 .venv 后重新运行：bash run.sh"
fi

# shellcheck disable=SC1091
. ".venv/bin/activate" || fail "激活 Python 虚拟环境失败。"

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-30}"
printf '正在安装 TuneAgent 全部依赖...\n'
if ! python -m pip install -e ".[all]" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn; then
  fail "依赖安装失败，请检查网络连接或尝试科学上网。按任意键退出。"
fi

printf '\n正在启动 TuneAgent...\n'
python scripts/interactive_cli.py
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  printf '\n[错误] TuneAgent 异常退出，退出码：%s\n' "$STATUS" >&2
  pause_before_exit
fi

exit "$STATUS"
