@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Action Install -WithCimco -Interactive
set "result=%errorlevel%"
echo.
if "%result%"=="3010" (echo Restart Windows and run Install.cmd again to finish verification.) else if not "%result%"=="0" echo Installation did not finish. Read the error above.
pause
exit /b %result%
