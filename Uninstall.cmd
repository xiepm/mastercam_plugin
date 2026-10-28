@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Action Uninstall -Interactive
set "result=%errorlevel%"
echo.
pause
exit /b %result%
