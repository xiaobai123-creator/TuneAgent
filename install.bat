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

set "PYTHON_EXE="
for /f "delims=" %%P in ('%PY_CMD% -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE goto :python_missing

set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn"

set "UV_EXE="
where uv >nul 2>&1
if not errorlevel 1 set "UV_EXE=uv"
if not defined UV_EXE if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE goto :try_pipx

echo 检测到 uv，正在安装 TuneAgent CLI...
"%UV_EXE%" tool install --force --editable ".[cli]"
if errorlevel 1 goto :uv_failed
"%UV_EXE%" tool update-shell >nul 2>&1
goto :done

:uv_failed
echo uv 安装失败，改用 pipx 重试...

:try_pipx
set "PIPX_EXE="
where pipx >nul 2>&1
if not errorlevel 1 set "PIPX_EXE=pipx"
if not defined PIPX_EXE if exist "%USERPROFILE%\.local\bin\pipx.exe" set "PIPX_EXE=%USERPROFILE%\.local\bin\pipx.exe"
if defined PIPX_EXE goto :pipx_install

"%PYTHON_EXE%" -m pipx --version >nul 2>&1
if not errorlevel 1 (
    set "PIPX_PY=%PYTHON_EXE%"
    goto :pipx_module
)

if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "PIPX_VENV=%LOCALAPPDATA%\TuneAgent\pipx-venv"
set "PIPX_PY=%PIPX_VENV%\Scripts\python.exe"

if not exist "%PIPX_PY%" (
    echo 正在准备 pipx...
    "%PYTHON_EXE%" -m venv "%PIPX_VENV%"
    if errorlevel 1 goto :pipx_failed
)

"%PIPX_PY%" -m pipx --version >nul 2>&1
if errorlevel 1 (
    echo 正在安装 pipx...
    "%PIPX_PY%" -m pip install --upgrade pipx -i "%PIP_INDEX_URL%" --trusted-host "%PIP_TRUSTED_HOST%"
    if errorlevel 1 goto :pipx_failed
)

:pipx_module
echo 正在安装 TuneAgent CLI（只安装命令行依赖）...
"%PIPX_PY%" -m pipx install --python "%PYTHON_EXE%" --editable ".[cli]" --force
if errorlevel 1 goto :install_failed
"%PIPX_PY%" -m pipx ensurepath
if errorlevel 1 echo [提示] 自动更新 PATH 失败，请把 pipx 提示的 bin 目录加入 PATH。
goto :done

:pipx_install
echo 正在安装 TuneAgent CLI（只安装命令行依赖）...
"%PIPX_EXE%" install --python "%PYTHON_EXE%" --editable ".[cli]" --force
if errorlevel 1 goto :install_failed
"%PIPX_EXE%" ensurepath
if errorlevel 1 echo [提示] 自动更新 PATH 失败，请把 pipx 提示的 bin 目录加入 PATH。

:done
echo.
echo 安装完成。
echo 请关闭这个窗口，重新打开终端，然后运行：
echo    tuneagent
echo.
echo 如果仍提示找不到命令，请把 uv 或 pipx 提示的 bin 目录加入 PATH，或直接运行：
echo    "%USERPROFILE%\.local\bin\tuneagent.exe"
echo.
pause
exit /b 0

:python_missing
echo.
echo [错误] 未检测到 Python 3.10 或更高版本。
echo 请先从 https://www.python.org/downloads/ 安装 Python，
echo 安装时勾选 "Add Python to PATH"，然后重新运行 install.bat。
echo.
pause
exit /b 1

:pipx_failed
echo.
echo [错误] 准备 pipx 失败。
echo 请检查网络连接；也可以直接双击 run.bat 使用项目内 .venv。
echo.
pause
exit /b 1

:install_failed
echo.
echo [错误] TuneAgent CLI 安装失败。
echo 请检查网络连接；也可以直接双击 run.bat 使用项目内 .venv。
echo.
pause
exit /b 1
