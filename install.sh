#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

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
    if command -v "$candidate" >/dev/null 2>&1; then
      path="$(command -v "$candidate")"
      if "$path" -c \
        'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1; then
        printf '%s\n' "$path"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(find_python)" || fail \
  "未检测到 Python 3.10 或更高版本。" \
  "请先安装 Python，并确认 python3 或 python 可以从终端运行。"

printf '使用 Python：%s\n' "$PYTHON"

export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
fi

if [ -n "$UV_BIN" ]; then
  printf '检测到 uv，正在安装 TuneAgent CLI...\n'
  if "$UV_BIN" tool install --force --editable ".[cli]"; then
    "$UV_BIN" tool update-shell >/dev/null 2>&1 || true
    printf '\n安装完成。请重新打开终端，然后运行：\n    tuneagent\n'
    printf '\n如果仍提示找不到命令，请把 %s/.local/bin 加入 PATH，或直接运行：\n' "$HOME"
    printf '    %s/.local/bin/tuneagent\n' "$HOME"
    exit 0
  fi
  printf 'uv 安装失败，改用 pipx 重试...\n'
fi

PIPX_VENV_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/tuneagent/pipx-venv"
PIPX_PY="$PIPX_VENV_DIR/bin/python"

if command -v pipx >/dev/null 2>&1; then
  PIPX_CMD=("$(command -v pipx)")
elif "$PYTHON" -m pipx --version >/dev/null 2>&1; then
  PIPX_CMD=("$PYTHON" -m pipx)
else
  if [ ! -x "$PIPX_PY" ]; then
    printf '正在准备 pipx...\n'
    "$PYTHON" -m venv "$PIPX_VENV_DIR" || fail \
      "创建 pipx 环境失败。" \
      "请确认 Python 的 venv 模块可用，例如 Ubuntu/Debian 可安装 python3-venv。"
  fi
  if ! "$PIPX_PY" -m pipx --version >/dev/null 2>&1; then
    printf '正在安装 pipx...\n'
    "$PIPX_PY" -m pip install --upgrade pipx || fail \
      "pipx 安装失败。" \
      "请检查网络连接，或先运行 bash run.sh 使用项目内 .venv。"
  fi
  PIPX_CMD=("$PIPX_PY" -m pipx)
fi

printf '正在安装 TuneAgent CLI（只安装命令行依赖）...\n'
if ! "${PIPX_CMD[@]}" install \
  --python "$PYTHON" \
  --editable ".[cli]" \
  --force; then
  fail \
    "TuneAgent CLI 安装失败。" \
    "请检查网络连接；也可以先运行 bash run.sh 使用项目内 .venv。"
fi

"${PIPX_CMD[@]}" ensurepath || true

printf '\n安装完成。请重新打开终端，然后运行：\n    tuneagent\n'
printf '\n如果仍提示找不到命令，请把 pipx 提示的 bin 目录加入 PATH，或直接运行：\n'
printf '    %s/.local/bin/tuneagent\n' "$HOME"
