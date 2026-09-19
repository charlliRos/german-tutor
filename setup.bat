@echo off
rem One-time setup on Windows: virtual environment, libraries, German voice, "gtutor" command.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist .venv\Scripts\python.exe (
    %PY% -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install --upgrade pip || goto :error
.venv\Scripts\python -m pip install -r requirements.txt || goto :error
.venv\Scripts\python tools\download_voice.py || goto :error
.venv\Scripts\python tools\download_speech_model.py || goto :error

rem Put bin\ on the user PATH so "gtutor" starts the app from any terminal.
rem Read and write the raw registry value, so entries like %%USERPROFILE%%\... stay unexpanded.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bin = (Resolve-Path 'bin').Path; $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true); $p = [string]$key.GetValue('Path', '', 'DoNotExpandEnvironmentNames'); if (($p -split ';') -contains $bin) { Write-Host 'gtutor is already on your PATH.' } else { $new = if ($p) { $p.TrimEnd(';') + ';' + $bin } else { $bin }; $key.SetValue('Path', $new, 'ExpandString'); [Environment]::SetEnvironmentVariable('GTUTOR_SETUP', '1', 'User'); [Environment]::SetEnvironmentVariable('GTUTOR_SETUP', $null, 'User'); Write-Host 'Added gtutor to your PATH.' }" || goto :error

echo.
echo Setup finished. Open a NEW terminal and type: gtutor
echo (or double-click run.bat)
exit /b 0

:error
echo Setup failed - see the messages above.
exit /b 1
