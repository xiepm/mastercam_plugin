@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Action Install -Interactive
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Installation did not finish. Read the error above.
pause
exit /b %result%
