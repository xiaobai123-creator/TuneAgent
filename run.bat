@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"

set "PY_CMD="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"

if not defined PY_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD goto :python_missing

if not exist ".venv\Scripts\python.exe" (
    echo 未检测到 .venv，正在创建虚拟环境...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :venv_failed
)

if not exist ".venv\Scripts\activate.bat" goto :activate_failed
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :activate_failed

set "PIP_DEFAULT_TIMEOUT=30"
echo 正在安装 TuneAgent 全部依赖...
python -m pip install --retries 2 -e ".[all]"
if errorlevel 1 goto :install_failed

echo.
echo 正在启动 TuneAgent...
python scripts\interactive_cli.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] TuneAgent 异常退出，退出码：%EXIT_CODE%
)
echo.
pause
exit /b %EXIT_CODE%

:python_missing
echo.
echo [错误] 未检测到 Python 3.10 或更高版本。
echo 请先从 https://www.python.org/downloads/ 安装 Python，
echo 安装时勾选 "Add Python to PATH"，然后重新双击 run.bat。
echo.
pause
exit /b 1

:venv_failed
echo.
echo [错误] 创建 Python 虚拟环境失败。
echo 请确认 Python 安装完整，并重新双击 run.bat。
echo.
pause
exit /b 1

:activate_failed
echo.
echo [错误] 虚拟环境不完整或无法激活。
echo 请删除 .venv 文件夹后重新双击 run.bat。
echo.
pause
exit /b 1

:install_failed
echo.
echo [错误] 依赖安装失败，可能是网络超时或 PyPI 无法访问。
echo 请检查网络后重新双击 run.bat。
echo.
pause
exit /b 1
