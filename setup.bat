@echo off
rem One-time setup on Windows: virtual environment, libraries, German voice.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist .venv\Scripts\python.exe (
    %PY% -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --upgrade pip || goto :error
.venv\Scripts\python -m pip install -r requirements.txt || goto :error
.venv\Scripts\python tools\download_voice.py || goto :error
echo.
echo Setup finished. Start the tutor with: run.bat
exit /b 0

:error
echo Setup failed - see the messages above.
exit /b 1
