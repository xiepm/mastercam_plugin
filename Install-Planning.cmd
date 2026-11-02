@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Planning.ps1" %*
exit /b %errorlevel%
