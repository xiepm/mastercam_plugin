param([string]$MastercamRoot,[string]$Workspace,[string]$CodexHome,[string]$Python)
$ErrorActionPreference='Stop'
$packageRoot=$PSScriptRoot
if (!$Workspace) { $Workspace=Join-Path $env:LOCALAPPDATA 'MastercamAgent\workspace' }
if (!$CodexHome) { $CodexHome=if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' } }
if (!$MastercamRoot) {
    $candidates=@((Join-Path $env:ProgramFiles 'Mastercam 2027'))
    foreach ($key in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
        $candidates+=@(Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'Mastercam 2027' -and $_.InstallLocation } | ForEach-Object InstallLocation)
    }
    $MastercamRoot=$candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'Mastercam.exe') } | Select-Object -First 1
    if (!$MastercamRoot) { $MastercamRoot=Read-Host 'Mastercam 2027 folder containing Mastercam.exe' }
}
if (!(Test-Path -LiteralPath (Join-Path $MastercamRoot 'Mastercam.exe'))) { throw 'Mastercam installation not found.' }
if (!$Python) {
    $launcher=Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { $Python=& $launcher.Source -3.11 -c 'import sys;print(sys.executable)' }
    if (!$Python) { $found=Get-Command python.exe -ErrorAction SilentlyContinue; if ($found) { $Python=$found.Source } }
}
if (!$Python) { throw 'Install Python 3.11 or newer from python.org, then run Install-AI again.' }
& $Python -c 'import sys;assert sys.version_info >= (3,11), "Python 3.11+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ required.' }
$venv=Join-Path $packageRoot '.ai-venv'
if (!(Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) { & $Python -m venv $venv; if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python environment.' } }
$agentPython=Join-Path $venv 'Scripts\python.exe'
& $agentPython -m pip install -r (Join-Path $packageRoot 'ai\environments\requirements-windows.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $agentPython (Join-Path $packageRoot 'ai\tools\install_agent.py') --mastercam-root $MastercamRoot --workspace $Workspace --codex-home $CodexHome
if ($LASTEXITCODE -ne 0) { throw 'Agent configuration failed; see the conflict or missing requirement above.' }
& $agentPython (Join-Path $packageRoot 'ai\tools\doctor.py') --config (Join-Path $Workspace 'plugin-ai-config.json')
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed. Install the matching plugin package with Install.cmd, then retry.' }
Write-Output 'AI configured. Restart Mastercam, reload Codex MCP tools, then use $mastercam-project.'
