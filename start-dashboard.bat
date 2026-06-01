@echo off
REM claudeshorts - one-shot dashboard launcher for Windows.
REM Double-click this file. Finds a Python 3.11+ interpreter, sets up a venv,
REM installs deps, then starts the local dashboard and opens it in your browser.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PORT=8000"
if not "%CLAUDESHORTS_PORT%"=="" set "PORT=%CLAUDESHORTS_PORT%"

REM --- find a Python 3.11+ interpreter ---
set "PYBIN="
for %%P in ("py -3.13" "py -3.12" "py -3.11" "py -3" "python3" "python") do (
  if not defined PYBIN (
    %%~P -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)" >nul 2>nul
    if !errorlevel! equ 0 set "PYBIN=%%~P"
  )
)
if not defined PYBIN (
  echo Python 3.11+ is required but was not found.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then re-run.
  pause
  exit /b 1
)
echo - Using Python via: %PYBIN%

REM --- (re)create the venv if missing or built with an older Python ---
set "RECREATE=0"
if exist ".venv" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo - Existing .venv uses an old Python - recreating...
    rmdir /s /q .venv
    set "RECREATE=1"
  )
) else (
  set "RECREATE=1"
)
if "%RECREATE%"=="1" (
  echo - Creating virtualenv ^(.venv^)...
  %PYBIN% -m venv .venv
)
call ".venv\Scripts\activate.bat"

REM --- install deps only if a core dependency is missing ---
python -c "import typer, fastapi, uvicorn, jinja2, anthropic, feedparser, yaml, httpx, dotenv" >nul 2>nul
if errorlevel 1 (
  echo - Installing Python dependencies ^(first run can take a minute^)...
  python -m pip install -q --upgrade pip
  python -m pip install -q -e .
)

python -m claudeshorts.cli init-db >nul

REM --- renderer deps (best-effort) ---
where node >nul 2>nul
if errorlevel 1 (
  echo   Warning: Node.js not found - the dashboard runs, but rendering needs Node ^(see renderer\^).
) else (
  if exist "renderer\package.json" if not exist "renderer\node_modules" (
    echo - Installing renderer dependencies ^(npm^)...
    pushd renderer
    call npm install --silent
    popd
  )
)

start "" "http://127.0.0.1:%PORT%"
echo.
echo Starting claudeshorts dashboard at http://127.0.0.1:%PORT%  (press Ctrl-C to stop)
python -m claudeshorts.cli serve --port %PORT%

endlocal
