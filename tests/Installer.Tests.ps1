$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
. (Join-Path $repo 'scripts\Package.Core.ps1')
$work=Join-Path ([IO.Path]::GetTempPath()) ('mc27-test-'+[guid]::NewGuid().ToString('N').Substring(0,8))
[void][IO.Directory]::CreateDirectory($work)
$script:Checks=[Collections.Generic.List[object]]::new()
function Check([string]$Name,[bool]$Condition) {
    $script:Checks.Add([pscustomobject]@{name=$Name;passed=$Condition})
    if (!$Condition) { throw "FAIL: $Name" }
    Write-Output "PASS: $Name"
}
function Must-Fail([string]$Name,[scriptblock]$Body) {
    $failed=$false
    try { & $Body | Out-Null } catch { $failed=$true }
    Check $Name $failed
}
function Fixture([string]$Name,[string]$Previous='') {
    $path=Join-Path $work $Name
    $root=Join-Path $path 'custom drive\Mastercam 2027'
    $config=Join-Path $path 'redirected documents\CONFIG'
    [void][IO.Directory]::CreateDirectory((Join-Path $root 'chooks'))
    [void][IO.Directory]::CreateDirectory($config)
    [IO.File]::WriteAllText((Join-Path $config 'mcamxm.config'),"001. Setting? keep`r`n16010. Startup? <APP_DIR_INSTALL>$Previous`r`n002. More? original`r`n",[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $config 'mcamx.config'),"001. Setting? keep`r`n16010. Startup? <APP_DIR_INSTALL>$Previous`r`n",[Text.Encoding]::Unicode)
    if ($Previous) { $p=Join-Safe $root $Previous;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($p));[IO.File]::WriteAllText($p,'old plugin') }
    [IO.File]::WriteAllText((Join-Path $root 'chooks\unrelated.dll'),'must stay')
    return [pscustomobject]@{root=$root;config=$config}
}
function Snapshot($Fixture) {
    $result=@{}
    foreach ($base in @($Fixture.root,$Fixture.config)) {
        foreach ($file in Get-ChildItem -LiteralPath $base -File -Recurse -Force) {
            if ($file.FullName -like '*\.MC2027PluginSuite\*') { continue }
            $result[$file.FullName]=Get-Sha $file.FullName
        }
    }
    return ($result.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Name+'='+$_.Value }) -join "`n"
}
try {
    $m=Read-Package $repo
    $payloadCount=@(Get-ChildItem -LiteralPath (Join-Path $repo 'payload') -File -Recurse).Count
    Check 'Full payload hashes verified' (@($m.files).Count -eq $payloadCount -and $payloadCount -gt 0)
    $f=Fixture 'full payload'
    $before=Snapshot $f
    $preview=Invoke-SuiteInstall $f.root $f.config $repo -Preview
    Check 'Preview writes nothing' (($preview.files -eq $payloadCount) -and (Snapshot $f) -eq $before -and !(Test-Path (Join-Path $f.root 'chooks\.MC2027PluginSuite')))
    Invoke-SuiteInstall $f.root $f.config $repo | Out-Null
    $r=Read-Receipt $f.root
    Assert-ReceiptClean $f.root $r -CheckConfigs
    Check 'Clean install at paths with spaces; both configs verified' (@($r.files).Count -eq $payloadCount -and @($r.configs).Count -eq 2)
    Check 'No previous hook / no machine IPC dependency' (!(Test-Path (Join-Path $f.root 'chooks\MC2027SuitePrevious.ft')))
    Check 'UTF-16 config encoding retained' (([IO.File]::ReadAllBytes((Join-Path $f.config 'mcamx.config')))[0] -eq 255)
    $initial=($r.files|ForEach-Object { $_.path+'='+$_.originalHash }) -join "`n"
    Invoke-SuiteInstall $f.root $f.config $repo | Out-Null
    $upgraded=Read-Receipt $f.root
    Check 'Upgrade does not create a startup self-loop' (!(Test-Path (Join-Path $f.root 'chooks\MC2027SuitePrevious.ft')))
    Check 'Repeat install retains original backup ownership' ((($upgraded.files|ForEach-Object { $_.path+'='+$_.originalHash }) -join "`n") -eq $initial)
    $target=Join-Safe $f.root $r.files[0].path
    $bytes=[IO.File]::ReadAllBytes($target)
    [IO.File]::WriteAllText($target,'user edit')
    Must-Fail 'Upgrade refuses modified installed file' { Invoke-SuiteInstall $f.root $f.config $repo }
    Must-Fail 'Uninstall refuses modified installed file' { Invoke-SuiteUninstall $f.root }
    Check 'Conflicting user edit preserved' ([IO.File]::ReadAllText($target) -eq 'user edit')
    [IO.File]::WriteAllBytes($target,$bytes)
    $snapshot=Snapshot $f
    $receipt=Join-Safe $f.root 'chooks/.MC2027PluginSuite/receipt.json'
    $receiptHash=Get-Sha $receipt
    $script:SuiteFaultAfter=7
    Must-Fail 'Injected partial upgrade fails' { Invoke-SuiteInstall $f.root $f.config $repo }
    $script:SuiteFaultAfter=-1
    Check 'Partial upgrade restores all file/config bytes and prior receipt' ((Snapshot $f) -eq $snapshot -and (Get-Sha $receipt) -eq $receiptHash)
    $metric=Join-Path $f.config 'mcamxm.config'
    $info=Read-Config $metric
    [IO.File]::WriteAllText($metric,$info.Text.Replace('002. More? original','002. More? user changed'),[Text.UTF8Encoding]::new($false))
    Invoke-SuiteUninstall $f.root | Out-Null
    Check 'Uninstall restores only startup and preserves later user settings' ([IO.File]::ReadAllText($metric).Contains('002. More? user changed') -and (Get-StartupPath (Read-Config $metric).Line) -eq '')
    [IO.File]::WriteAllText($metric,[IO.File]::ReadAllText($metric).Replace('002. More? user changed','002. More? original'),[Text.UTF8Encoding]::new($false))
    Check 'Uninstall restores exact initial file set / bytes' ((Snapshot $f) -eq $before)
    Check 'Receipt marked inactive, original backups retained' ($null -eq (Read-Receipt $f.root) -and (Test-Path (Join-Safe $f.root 'chooks/.MC2027PluginSuite/history')))

    $f=Fixture 'previous startup' 'chooks\OldHook\startup.dll'
    $before=Snapshot $f
    $collision=Join-Safe $f.root $m.files[0].path
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($collision))
    [IO.File]::WriteAllText($collision,'previous third party file')
    $before=Snapshot $f
    Invoke-SuiteInstall $f.root $f.config $repo | Out-Null
    Check 'Existing startup chained without copying its binary' ([IO.File]::ReadAllText((Join-Safe $f.root 'chooks/MC2027SuitePrevious.ft')).Contains('chooks\OldHook\startup.dll'))
    Invoke-SuiteInstall $f.root $f.config $repo | Out-Null
    $r=Read-Receipt $f.root
    $saved=Join-Safe $f.root (@($r.files|Where-Object path -EQ $m.files[0].path)[0].originalBackup)
    $savedBytes=[IO.File]::ReadAllBytes($saved)
    [IO.File]::WriteAllText($saved,'corrupt')
    Must-Fail 'Uninstall verifies original backup before any write' { Invoke-SuiteUninstall $f.root }
    [IO.File]::WriteAllBytes($saved,$savedBytes)
    $english=Join-Path $f.config 'mcamx.config';$englishBytes=[IO.File]::ReadAllBytes($english)
    [IO.File]::WriteAllText($english,"16010. Startup? <APP_DIR_INSTALL>chooks\Other.dll`r`n",[Text.Encoding]::Unicode)
    Must-Fail 'External startup change stops uninstall' { Invoke-SuiteUninstall $f.root }
    [IO.File]::WriteAllBytes($english,$englishBytes)
    Invoke-SuiteUninstall $f.root | Out-Null
    Check 'Previous files and hook restore exactly after two installs' ((Snapshot $f) -eq $before)

    $f=Fixture 'different hooks'
    [IO.File]::WriteAllText((Join-Path $f.config 'mcamx.config'),"16010. Startup? <APP_DIR_INSTALL>chooks\Another.dll`r`n")
    $before=Snapshot $f
    Must-Fail 'Different metric/inch hooks fail before writing' { Invoke-SuiteInstall $f.root $f.config $repo }
    Check 'Differing hook rejection changes nothing' ((Snapshot $f) -eq $before)
    Invoke-SuiteInstall $f.root $f.config $repo -SkipStartup | Out-Null
    Check 'Manual-load installation leaves both configs unchanged' (@((Read-Receipt $f.root).configs).Count -eq 0)
    Invoke-SuiteUninstall $f.root | Out-Null
    Check 'Manual-load uninstall restores original file set' ((Snapshot $f) -eq $before)
    Must-Fail 'Path traversal blocked' { Join-Safe $f.root '..\outside.dll' }
    Must-Fail 'Alternate data stream blocked' { Join-Safe $f.root 'chooks/file.dll:stream' }
    Must-Fail 'Absolute manifest path blocked' { Join-Safe $f.root 'C:\outside.dll' }
    $f=Fixture 'first-install rollback'
    $before=Snapshot $f;$script:SuiteFaultAfter=5
    Must-Fail 'Injected first install failure' { Invoke-SuiteInstall $f.root $f.config $repo }
    $script:SuiteFaultAfter=-1
    Check 'Failed first install leaves no owned payload or receipt' ((Snapshot $f) -eq $before -and $null -eq (Read-Receipt $f.root))

    $f=Fixture 'recover interrupted install'
    $target=Join-Safe $f.root 'chooks/unrelated.dll'
    $backup=Join-Safe $f.root 'chooks/.MC2027PluginSuite/history/interrupted/0000.bak'
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($backup))
    [IO.File]::Copy($target,$backup)
    [IO.File]::WriteAllText($target,'partial installed content')
    $newHash=Get-Sha $target
    $journal=Join-Safe $f.root 'chooks/.MC2027PluginSuite/pending.json'
    Write-Json $journal ([pscustomobject]@{schemaVersion=1;root=$f.root;entries=@([pscustomobject]@{path=$target;backup=$backup;oldHash=(Get-Sha $backup);newHash=$newHash})})
    [IO.File]::WriteAllText($target,'later manual edit')
    Must-Fail 'Crash recovery protects edits made after interruption' { Restore-Journal $f.root $journal -StrictCurrent }
    Check 'Recovery conflict preserves manual edit' ([IO.File]::ReadAllText($target) -eq 'later manual edit')
    [IO.File]::WriteAllText($target,'partial installed content')
    Restore-Journal $f.root $journal -StrictCurrent
    Check 'Explicit recovery restores verified snapshot and clears pending marker' ((Get-Sha $target) -eq (Get-Sha $backup) -and !(Test-Path $journal))

    $small=Join-Path $work 'small-package'
    [void][IO.Directory]::CreateDirectory((Join-Path $small 'catalog'))
    $smallManifest=Get-Content (Join-Path $repo 'catalog/package.json') -Raw|ConvertFrom-Json
    $smallManifest.files=@($smallManifest.files|Select-Object -First 3)
    foreach($file in $smallManifest.files) {
        $to=Join-Safe (Join-Path $small 'payload') $file.path
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to))
        [IO.File]::Copy((Join-Safe (Join-Path $repo 'payload') $file.path),$to)
    }
    $smallJson=Join-Path $small 'catalog/package.json'
    Write-Json $smallJson $smallManifest
    $f=Fixture 'obsolete file upgrade'
    $obsolete=$smallManifest.files[2].path
    $to=Join-Safe $f.root $obsolete
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to))
    [IO.File]::WriteAllText($to,'pre-suite content')
    $before=Snapshot $f
    Invoke-SuiteInstall $f.root $f.config $small | Out-Null
    Remove-Item -LiteralPath (Join-Safe (Join-Path $small 'payload') $obsolete)
    $smallManifest.files=@($smallManifest.files|Select-Object -First 2)
    Write-Json $smallJson $smallManifest
    Invoke-SuiteInstall $f.root $f.config $small | Out-Null
    Check 'Upgrade restores obsolete payload file to its original content' ([IO.File]::ReadAllText($to) -eq 'pre-suite content')
    Invoke-SuiteUninstall $f.root | Out-Null
    Check 'Uninstall after file-set change preserves exact baseline' ((Snapshot $f) -eq $before)
    $unicodeName=-join ([char[]]@(0x4e2d,0x6587))
    $f=Fixture $unicodeName 'chooks\previous.dll'
    $metricConfig=Join-Path $f.config 'mcamxm.config'
    $localized=[IO.File]::ReadAllText($metricConfig).Replace('Startup?',(-join ([char[]]@(0x542f,0x52a8)))+'?')
    [IO.File]::WriteAllText($metricConfig,$localized,[Text.UTF8Encoding]::new($false))
    $before=Snapshot $f
    Invoke-SuiteInstall $f.root $f.config $small | Out-Null
    $unicodeReceipt=Read-Receipt $f.root
    Assert-ReceiptClean $f.root $unicodeReceipt -CheckConfigs
    Check 'UTF8 JSON receipt preserves localized paths and Chinese startup labels in PowerShell 5' ($unicodeReceipt.root -eq $f.root -and $unicodeReceipt.configs[0].installedLine.Contains((-join ([char[]]@(0x542f,0x52a8)))))
    Invoke-SuiteUninstall $f.root | Out-Null
    Check 'Localized installation uninstalls with exact original config bytes' ((Snapshot $f) -eq $before)
    $bad=Join-Safe (Join-Path $small 'payload') $smallManifest.files[0].path
    [IO.File]::WriteAllText($bad,'tamper')
    Must-Fail 'Corrupt download rejected before installation' { Invoke-SuiteInstall $f.root $f.config $small }
    Check 'Rejected corrupt package leaves destination unchanged' ((Snapshot $f) -eq $before)

    $report=[ordered]@{suite='Portable installer';date='2026-10-28';powershell=$PSVersionTable.PSVersion.ToString();payloadFiles=$payloadCount;checks=@($script:Checks.ToArray());passed=$true;nativeHostUsed=$false}
    [void][IO.Directory]::CreateDirectory((Join-Path $repo 'validation'))
    Write-Json (Join-Path $repo ('validation/installer-'+$PSVersionTable.PSVersion.Major+'.json')) $report
    Write-Output ("ALL PASS: {0} checks" -f $script:Checks.Count)
} finally { $script:SuiteFaultAfter=-1 }
