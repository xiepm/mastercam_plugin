param([string]$Output)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
. (Join-Path $repo 'scripts\Package.Core.ps1')
. (Join-Path $repo 'scripts\Cimco.ps1')
$checks=[Collections.Generic.List[object]]::new()
function Check([string]$Name,[bool]$OK) { $checks.Add(@{name=$Name;passed=$OK});if(!$OK){throw $Name} }
function MustFail([string]$Name,[scriptblock]$Body) { $failed=$false;try{& $Body}catch{$failed=$true};Check $Name $failed }
$fixture=Join-Path $env:TEMP ('mc27-cimco-'+[guid]::NewGuid().ToString('N').Substring(0,8))
$mc=Join-Path $fixture 'Mastercam 2027'
[void][IO.Directory]::CreateDirectory((Join-Path $mc 'chooks'))
$script:testSpec=Get-CimcoSpec
$realUrl=$script:testSpec.url
foreach($file in $script:testSpec.files) {
    $p=Join-Safe $mc $file.path
    [IO.File]::WriteAllText($p,'fixture '+$file.path)
    $file.sha256=Get-Sha $p
}
$script:testRegistration=[pscustomobject]@{DisplayVersion=$script:testSpec.version;InstallLocation=$fixture}
foreach ($name in @('CIMCOSimulation.exe','SimulationWindow.dll','Msg/License.txt')) {
    $file=Join-Safe $fixture $name;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file));[IO.File]::WriteAllText($file,'fixture')
}
$script:signatureOK=$true
function Get-CimcoSpec { return $script:testSpec }
function Get-CimcoRegistration { return $script:testRegistration }
function Test-CimcoSignature([string]$Path) { return $script:signatureOK }
try {
    Check 'Download is pinned to official HTTPS URL' ($realUrl -like 'https://downloads.mastercam.dk/*26.9.11.46240*')
    Check 'Complete verified installation skipped' ((Get-CimcoState $mc).action -eq 'Skip')
    $sharedFile=Join-Safe $fixture 'SimulationWindow.dll';Remove-Item -LiteralPath $sharedFile
    Check 'Missing shared runtime prevents a false installed result' ((Get-CimcoState $mc).action -eq 'Stop')
    [IO.File]::WriteAllText($sharedFile,'fixture')
    $before=($script:testSpec.files | ForEach-Object { Get-Sha (Join-Safe $mc $_.path) }) -join ','
    $result=Invoke-CimcoInstall $mc 'must-not-execute.exe' (Join-Path $fixture 'report')
    Check 'Skip path does not require or execute installer' ($result.state -eq 'AlreadyInstalled' -and !$result.changed)
    Check 'Skip path leaves all CIMCO files unchanged' ((($script:testSpec.files | ForEach-Object { Get-Sha (Join-Safe $mc $_.path) }) -join ',') -eq $before)
    $script:signatureOK=$false
    Check 'Invalid installed signature is preserved for repair' ((Get-CimcoState $mc).action -eq 'Stop')
    $script:signatureOK=$true
    $dll=Join-Safe $mc 'chooks/CIMCOSimulation.dll'
    $old=[IO.File]::ReadAllBytes($dll);[IO.File]::AppendAllText($dll,'tamper')
    Check 'Modified pinned DLL is preserved for repair' ((Get-CimcoState $mc).action -eq 'Stop')
    [IO.File]::WriteAllBytes($dll,$old)
    $script:testRegistration.DisplayVersion='27.0.0.0'
    Check 'Valid newer install is not downgraded' ((Get-CimcoState $mc).action -eq 'Skip')
    $ft=Join-Safe $mc 'chooks/CIMCOSimulation.ft';$ftBytes=[IO.File]::ReadAllBytes($ft);Remove-Item -LiteralPath $ft
    Check 'Incomplete newer install is not downgraded' ((Get-CimcoState $mc).action -eq 'Stop')
    [IO.File]::WriteAllBytes($ft,$ftBytes)
    $script:testRegistration.DisplayVersion='25.0.0.0'
    Check 'Older registration selects official upgrade' ((Get-CimcoState $mc).action -eq 'Install')
    $script:testRegistration=$null
    Check 'Unregistered existing DLLs are not overwritten' ((Get-CimcoState $mc).action -eq 'Stop')
    foreach($f in $script:testSpec.files){Remove-Item -LiteralPath (Join-Safe $mc $f.path)}
    Check 'Missing installation selects official install' ((Get-CimcoState $mc).action -eq 'Install')
    $args=Get-CimcoArguments 'C:\Logs with spaces\install.log'
    Check 'Installer selects 2027 component only' ($args.Contains('/COMPONENTS="general,mcam\v27"') -and $args.Contains('/TYPE=custom'))
    Check 'Installer cannot close Mastercam or reboot Windows' ($args.Contains('/NOCLOSEAPPLICATIONS') -and $args.Contains('/NORESTART') -and $args.Contains('/RESTARTEXITCODE=3010'))
    MustFail 'Installer arguments reject quote injection' {Get-CimcoArguments 'C:\bad" /silent'}
    MustFail 'Wrong installer hash is rejected before signature/execute' {Assert-CimcoInstaller (Join-Path $fixture 'report\cimco-result.json')}
    function Get-ItemProperty { param($LiteralPath,$ErrorAction) return [pscustomobject]@{Directory=$mc} }
    Assert-CimcoHostRegistration $mc
    Check 'Matching official Mastercam registry root accepted' $true
    MustFail 'Different target root rejected before vendor installation' {Assert-CimcoHostRegistration (Join-Path $fixture 'Different Mastercam')}
    $report=[ordered]@{suite='CIMCO orchestration';powershell=$PSVersionTable.PSVersion.ToString();passed=$true;checks=$checks.ToArray();vendorInstallerExecuted=$false;note='Isolated filesystem and registration/signature stubs; real signature/download verification is recorded separately.'}
    if($Output){Write-Json $Output $report}
    $report | ConvertTo-Json -Depth 8
} finally {
    # The isolated fixture is deliberately retained for diagnosing failed installer tests.
}
