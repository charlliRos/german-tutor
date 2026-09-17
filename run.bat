@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Please run setup.bat first.
    goto :end
)
.venv\Scripts\python tutor.py %*
:end
rem Keep the window open when started by double-click, so messages can be read.
echo %cmdcmdline% | findstr /i /c:"%~nx0" >nul && pause
