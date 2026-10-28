@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Action CheckPackage
if errorlevel 1 goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Action Verify -Interactive
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Verification failed. Read the error above.
pause
exit /b 1
