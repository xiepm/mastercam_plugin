param([string]$Workspace,[string]$CodexHome,[string]$Python,[string]$KnowledgeRoot,[string]$P01Python,[string]$P01Distro='Ubuntu-22.04')
$ErrorActionPreference='Stop'
if (!$Workspace) { $Workspace=Join-Path $env:LOCALAPPDATA 'MastercamAgent\workspace' }
if (!$CodexHome) { $CodexHome=if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex' } }
if (!$Python) {
    $launcher=Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { $Python=& $launcher.Source -3.11 -c 'import sys;print(sys.executable)' }
    if (!$Python) { $found=Get-Command python.exe -ErrorAction SilentlyContinue; if ($found) { $Python=$found.Source } }
}
if (!$Python) { throw 'Python 3.11+ is required.' }
& $Python -c 'import sys;assert sys.version_info >= (3,11)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
$venv=Join-Path $PSScriptRoot '.planning-venv'
$agentPython=Join-Path $venv 'Scripts\python.exe'
if (!(Test-Path -LiteralPath $agentPython)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create planning environment.' }
}
& $agentPython -m pip install -r (Join-Path $PSScriptRoot 'ai\environments\requirements-planning.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Planning dependency installation failed.' }
$installArgs=@((Join-Path $PSScriptRoot 'ai\tools\planning.py'),'install','--workspace',$Workspace,'--codex-home',$CodexHome)
if ($KnowledgeRoot) { $installArgs+=@('--knowledge-root',$KnowledgeRoot) }
if ($P01Python) { $installArgs+=@('--p01-python',$P01Python,'--p01-distro',$P01Distro) }
& $agentPython @installArgs
if ($LASTEXITCODE -ne 0) { throw 'Planning configuration failed.' }
Write-Output 'Planning Skill installed. Configure an authorized knowledge root before real-part planning; see docs/PLANNING_WORKFLOW.md.'
