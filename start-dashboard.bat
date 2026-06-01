@echo off
REM claudeshorts - one-shot dashboard launcher for Windows.
REM Double-click this file. It sets up a venv, installs deps, then starts the
REM local dashboard and opens it in your browser.
setlocal
cd /d "%~dp0"

set "PORT=8000"
if not "%CLAUDESHORTS_PORT%"=="" set "PORT=%CLAUDESHORTS_PORT%"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required ^(not found on PATH^).
  pause
  exit /b 1
)

if not exist ".venv" (
  echo - Creating virtualenv ^(.venv^)...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"

python -c "import claudeshorts" 2>nul
if errorlevel 1 (
  echo - Installing Python dependencies...
  python -m pip install -q --upgrade pip
  python -m pip install -q -e .
)

python -m claudeshorts.cli init-db >nul

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
