[CmdletBinding()]
param(
    [ValidateSet('Install','Preview','Verify','Uninstall','Recover','CheckPackage')][string]$Action='Install',
    [string]$MastercamRoot,
    [string]$ConfigDirectory,
    [switch]$SkipStartup,
    [switch]$Interactive
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'scripts\Package.Core.ps1')
try {
    if ($Action -eq 'CheckPackage') {
        $m=Read-Package $PSScriptRoot
        Write-Output ("Package OK: {0}; {1} files" -f $m.version,@($m.files).Count)
        exit 0
    }
    if (!$MastercamRoot) {
        $candidates=[Collections.Generic.List[string]]::new()
        foreach ($base in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
            foreach ($item in Get-ItemProperty $base -ErrorAction SilentlyContinue) {
                if ($item.PSObject.Properties['DisplayName'] -and $item.DisplayName -match 'Mastercam.*2027' -and $item.PSObject.Properties['InstallLocation'] -and $item.InstallLocation) { $candidates.Add($item.InstallLocation) }
            }
        }
        $candidates.Add((Join-Path $env:ProgramFiles 'Mastercam 2027'))
        $valid=@($candidates | Select-Object -Unique | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'Mastercam.exe') -PathType Leaf })
        if ($valid.Count -eq 1) { $MastercamRoot=$valid[0] }
        elseif ($Interactive) { $MastercamRoot=(Read-Host 'Mastercam 2027 folder (contains Mastercam.exe)').Trim('"') }
        else { throw 'Cannot uniquely detect Mastercam 2027. Supply -MastercamRoot.' }
    }
    $MastercamRoot=[IO.Path]::GetFullPath($MastercamRoot).TrimEnd('\')
    Assert-NoReparse $MastercamRoot
    if (!(Test-Path -LiteralPath (Join-Path $MastercamRoot 'Mastercam.exe') -PathType Leaf)) { throw 'Mastercam.exe not found in the selected folder.' }
    $api=Join-Path $MastercamRoot 'NETHook3_0.dll'
    if ([Reflection.AssemblyName]::GetAssemblyName($api).Version.Major -ne 29) { throw 'Only Mastercam 2027 / API29 is supported.' }
    if (!$ConfigDirectory) { $ConfigDirectory=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'My Mastercam 2027\Mastercam\CONFIG' }
    $ConfigDirectory=[IO.Path]::GetFullPath($ConfigDirectory).TrimEnd('\')
    if ($Action -in @('Install','Uninstall','Recover')) {
        if (Get-Process -Name Mastercam -ErrorAction SilentlyContinue) { throw 'Close Mastercam normally before installing or uninstalling.' }
        $admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (!$admin -and $Interactive) {
            foreach ($arg in @($PSScriptRoot,$MastercamRoot,$ConfigDirectory)) { if ($arg -match '["\r\n]') { throw 'Unsupported path characters.' } }
            $args='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Action '+$Action+' -MastercamRoot "'+$MastercamRoot+'" -ConfigDirectory "'+$ConfigDirectory+'"'
            if ($SkipStartup) { $args+=' -SkipStartup' }
            $p=Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs -Wait -PassThru
            exit $p.ExitCode
        }
    }
    $pending=Join-Safe $MastercamRoot 'chooks/.MC2027PluginSuite/pending.json'
    if ($Action -ne 'Recover' -and (Test-Path -LiteralPath $pending)) { throw 'Interrupted installation detected. Run -Action Recover first.' }
    switch ($Action) {
        'Preview' { Invoke-SuiteInstall $MastercamRoot $ConfigDirectory $PSScriptRoot -Preview -SkipStartup:$SkipStartup | Format-List }
        'Install' {
            Invoke-SuiteInstall $MastercamRoot $ConfigDirectory $PSScriptRoot -SkipStartup:$SkipStartup | Format-List
            Write-Output 'Restart Mastercam. Tabs: LittleBee / Workshop / X+ Tools / MP Design Tools.'
        }
        'Verify' {
            $r=Read-Receipt $MastercamRoot
            if (!$r) { throw 'No active installation receipt.' }
            Assert-ReceiptClean $MastercamRoot $r -CheckConfigs
            Write-Output ("Installed files and startup: OK ({0} files)" -f @($r.files).Count)
        }
        'Uninstall' { Invoke-SuiteUninstall $MastercamRoot | Format-List }
        'Recover' {
            if (!(Test-Path -LiteralPath $pending)) { throw 'No interrupted transaction found.' }
            Restore-Journal $MastercamRoot $pending -StrictCurrent
            Write-Output 'Previous installation state restored. Run Verify or Install next.'
        }
    }
    if ($Action -in @('Install','Preview')) {
        $m=Read-Package $PSScriptRoot
        $mismatch=@($m.nativeBuild | Where-Object { (Get-Sha (Join-Safe $MastercamRoot $_.path)) -ne $_.sha256 })
        if ($mismatch.Count) { Write-Warning 'This Mastercam build differs from the tested native bridge build. Porsche healing/hole interfaces may reject it. See docs/COMPATIBILITY.md.' }
    }
    exit 0
}
catch { Write-Error $_ -ErrorAction Continue; exit 1 }
