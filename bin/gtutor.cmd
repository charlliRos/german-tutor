@echo off
rem Launcher so "gtutor" works from any terminal (setup.bat puts this folder on PATH).
if not exist "%~dp0..\.venv\Scripts\python.exe" (
    echo German tutor is not set up yet. Run setup.bat in "%~dp0.." first.
    exit /b 1
)
"%~dp0..\.venv\Scripts\python.exe" "%~dp0..\tutor.py" %*
