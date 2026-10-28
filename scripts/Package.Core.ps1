Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$script:SuiteStartup = 'chooks\MC2027SuiteStartup\MC2027SuiteStartup.dll'
$script:SuiteFaultAfter = -1 # Test harness only; no public installer switch.

function Get-Sha([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    return $null
}
function Join-Safe([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)|:') { throw "Unsafe relative path: $Relative" }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (!$path.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "Path outside root: $Relative" }
    Assert-NoReparse $path
    return $path
}
function Assert-NoReparse([string]$Path) {
    $p = [IO.Path]::GetFullPath($Path)
    while ($p) {
        if (Test-Path -LiteralPath $p) {
            if ((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point is not allowed: $p" }
        }
        $p = [IO.Path]::GetDirectoryName($p)
    }
}
function Write-Atomic([string]$Path, [byte[]]$Bytes) {
    Assert-NoReparse $Path
    $dir = [IO.Path]::GetDirectoryName($Path)
    [void][IO.Directory]::CreateDirectory($dir)
    $temp = Join-Path $dir ([IO.Path]::GetFileName($Path)+'.'+[guid]::NewGuid().ToString('N')+'.tmp')
    try { [IO.File]::WriteAllBytes($temp,$Bytes); Move-Item -LiteralPath $temp -Destination $Path -Force }
    finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
}
function Write-Json([string]$Path, $Value) {
    Write-Atomic $Path ([Text.UTF8Encoding]::new($true).GetBytes(($Value | ConvertTo-Json -Depth 20)))
}
function Read-Config([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $offset = 0; $preamble = [byte[]]@(); $encoding = [Text.UTF8Encoding]::new($false,$true)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) { $offset=3; $preamble=[byte[]]@(239,187,191) }
    elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 255 -and $bytes[1] -eq 254) { $offset=2; $preamble=[byte[]]@(255,254); $encoding=[Text.Encoding]::Unicode }
    elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 254 -and $bytes[1] -eq 255) { $offset=2; $preamble=[byte[]]@(254,255); $encoding=[Text.Encoding]::BigEndianUnicode }
    try { $text=$encoding.GetString($bytes,$offset,$bytes.Length-$offset) }
    catch { $encoding=[Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage); $text=$encoding.GetString($bytes) }
    $lines=[regex]::Matches($text,'(?m)^16010\.[^\r\n]*')
    if ($lines.Count -ne 1) { throw "Expected one startup setting (16010) in: $Path" }
    return [pscustomobject]@{Text=$text;Encoding=$encoding;Preamble=$preamble;Line=$lines[0].Value;Path=$Path}
}
function Config-Bytes($Info,[string]$Line) {
    $m=[regex]::Match($Info.Text,'(?m)^16010\.[^\r\n]*')
    $text=$Info.Text.Substring(0,$m.Index)+$Line+$Info.Text.Substring($m.Index+$m.Length)
    return [byte[]]($Info.Preamble + $Info.Encoding.GetBytes($text))
}
function Get-StartupPath([string]$Line) {
    if ($Line -match '<APP_DIR_INSTALL>(.*)$') { return $Matches[1].Trim() }
    if ($Line -match '\.dll|<[^>]+>') { throw "Unsupported existing startup format: $Line" }
    return ''
}
function New-StartupLine([string]$Line) {
    if ($Line -match '<APP_DIR_INSTALL>') { return $Line.Substring(0,$Line.IndexOf('<APP_DIR_INSTALL>'))+'<APP_DIR_INSTALL>'+$script:SuiteStartup }
    return $Line.TrimEnd()+' <APP_DIR_INSTALL>'+$script:SuiteStartup
}
function Read-Receipt([string]$Root) {
    $path=Join-Safe $Root 'chooks\.MC2027PluginSuite\receipt.json'
    if (!(Test-Path -LiteralPath $path)) { return $null }
    $r=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($r.schemaVersion -ne 1 -or $r.root -ne [IO.Path]::GetFullPath($Root).TrimEnd('\')) { throw 'Receipt does not match the selected Mastercam directory.' }
    if (!$r.active) { return $null }
    return $r
}
function Read-Package([string]$PackageRoot) {
    $manifest=Get-Content -LiteralPath (Join-Path $PackageRoot 'catalog\package.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or @($manifest.files).Count -lt 1) { throw 'Invalid package manifest.' }
    $seen=@{}
    foreach ($f in $manifest.files) {
        if ($f.path -notmatch '^chooks/' -or $f.path -match '^chooks/\.MC2027PluginSuite/' -or $f.path -eq 'chooks/MC2027SuitePrevious.ft' -or $seen.ContainsKey($f.path)) { throw "Invalid or duplicate payload path: $($f.path)" }
        $seen[$f.path]=$true
        $source=Join-Safe (Join-Path $PackageRoot 'payload') $f.path
        if ((Get-Sha $source) -ne $f.sha256) { throw "Package hash mismatch: $($f.path)" }
        if ((Get-Item -LiteralPath $source).Length -ne $f.bytes) { throw "Package length mismatch: $($f.path)" }
    }
    $actual=@(Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'payload') -File -Recurse -Force)
    if ($actual.Count -ne @($manifest.files).Count) { throw 'Unexpected files in payload. Extract a fresh release archive.' }
    return $manifest
}
function Assert-ReceiptClean([string]$Root,$Receipt,[switch]$CheckConfigs) {
    foreach ($f in $Receipt.files) {
        $path=Join-Safe $Root $f.path
        if ((Get-Sha $path) -ne $f.installedHash) { throw "Installed file changed or missing; preserve your changes first: $path" }
        if ($f.originalBackup) {
            $saved=Join-Safe $Root $f.originalBackup
            if ((Get-Sha $saved) -ne $f.originalHash) { throw "Original backup missing or changed: $saved" }
        }
    }
    if ($CheckConfigs) {
        foreach ($c in $Receipt.configs) {
            Assert-NoReparse $c.path
            if ((Read-Config $c.path).Line -ne $c.installedLine) { throw "Startup was changed by another installer: $($c.path). No changes were made." }
        }
    }
}
function Invoke-FileTransaction([string]$Root,$Actions,[string]$ReceiptPath,$NewReceipt) {
    $state=Join-Safe $Root 'chooks\.MC2027PluginSuite'
    $pending=Join-Path $state 'pending.json'
    if (Test-Path -LiteralPath $pending) { throw 'An interrupted transaction exists. Run Manage.ps1 -Action Recover first.' }
    $id=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[guid]::NewGuid().ToString('N')
    $folder=Join-Path $state ('history\'+$id)
    [void][IO.Directory]::CreateDirectory($folder)
    $journal=[Collections.Generic.List[object]]::new()
    $index=0
    foreach ($a in $Actions) {
        Assert-NoReparse $a.path
        $snapshot=$null; $oldHash=Get-Sha $a.path
        if (Test-Path -LiteralPath $a.path) {
            if (!(Test-Path -LiteralPath $a.path -PathType Leaf)) { throw "Destination is not a file: $($a.path)" }
            $snapshot=Join-Path $folder ($index.ToString('D4')+'.bak')
            [IO.File]::Copy($a.path,$snapshot,$false)
        }
        $journal.Add([pscustomobject]@{path=$a.path;backup=$snapshot;oldHash=$oldHash;newHash=$a.hash})
        if ($a.record -and !$a.record.originalRecorded) {
            $a.record.originalRecorded=$true
            $a.record.originalHash=$oldHash
            if ($snapshot) { $a.record.originalBackup=$snapshot.Substring($Root.TrimEnd('\').Length+1).Replace('\','/') }
        }
        $index++
    }
    $receiptBytes=if (Test-Path -LiteralPath $ReceiptPath) { [IO.File]::ReadAllBytes($ReceiptPath) } else { $null }
    $receiptBackup=$null
    if ($receiptBytes) { $receiptBackup=Join-Path $folder 'receipt.bak'; [IO.File]::WriteAllBytes($receiptBackup,$receiptBytes) }
    $newReceiptAction=New-Action $ReceiptPath ([Text.UTF8Encoding]::new($false).GetBytes(($NewReceipt|ConvertTo-Json -Depth 20)))
    $journal.Add([pscustomobject]@{path=$ReceiptPath;backup=$receiptBackup;oldHash=(Get-Sha $ReceiptPath);newHash=$newReceiptAction.hash})
    # All backups and the journal are durable before the first destination write.
    Write-Json $pending ([pscustomobject]@{schemaVersion=1;root=$Root;entries=@($journal.ToArray())})
    $count=0
    try {
        foreach ($a in $Actions) {
            if ($script:SuiteFaultAfter -eq $count) { throw 'Injected transaction failure.' }
            if ($null -eq $a.bytes) { if (Test-Path -LiteralPath $a.path) { Remove-Item -LiteralPath $a.path -Force } }
            else { Write-Atomic $a.path $a.bytes }
            if ((Get-Sha $a.path) -ne $a.hash) { throw "Destination verification failed: $($a.path)" }
            $count++
        }
        Write-Atomic $ReceiptPath $newReceiptAction.bytes
        Move-Item -LiteralPath $pending -Destination (Join-Path $folder 'completed.json')
    }
    catch {
        $errorRecord=$_
        Restore-Journal $Root $pending
        throw $errorRecord
    }
}
function Restore-Journal([string]$Root,[string]$Path,[switch]$StrictCurrent) {
    $j=Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($j.root -ne $Root -or $j.schemaVersion -ne 1) { throw 'Recovery journal mismatch.' }
    # Recovery only targets paths from this local transaction; verify every backup first.
    foreach ($e in $j.entries) {
        Assert-NoReparse $e.path
        if ($StrictCurrent) {
            $current=Get-Sha $e.path
            if ($current -ne $e.oldHash -and $current -ne $e.newHash) { throw "File changed after interruption; preserve this change before recovery: $($e.path)" }
        }
        $inside=$e.path.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)
        if (!$inside -and [IO.Path]::GetFileName($e.path) -notin @('mcamxm.config','mcamx.config')) { throw 'Invalid recovery target.' }
        if ($e.backup) {
            Assert-NoReparse $e.backup
            if (!$e.backup.StartsWith($Root+'\chooks\.MC2027PluginSuite\history\',[StringComparison]::OrdinalIgnoreCase) -or (Get-Sha $e.backup) -ne $e.oldHash) { throw 'Recovery backup mismatch.' }
        }
    }
    $entries=@($j.entries)
    [array]::Reverse($entries)
    foreach ($e in $entries) {
        if ($e.backup) { Write-Atomic $e.path ([IO.File]::ReadAllBytes($e.backup)) }
        elseif (Test-Path -LiteralPath $e.path) { Remove-Item -LiteralPath $e.path -Force }
    }
    Move-Item -LiteralPath $Path -Destination ($Path+'.recovered-'+[guid]::NewGuid().ToString('N'))
}
function New-Action([string]$Path,[byte[]]$Bytes,$Record=$null) {
    $hash=$null
    if ($null -ne $Bytes) {
        $alg=[Security.Cryptography.SHA256]::Create()
        try { $hash=([BitConverter]::ToString($alg.ComputeHash($Bytes))).Replace('-','') } finally { $alg.Dispose() }
    }
    return [pscustomobject]@{path=$Path;bytes=$Bytes;hash=$hash;record=$Record}
}
function Invoke-SuiteInstall([string]$Root,[string]$ConfigDirectory,[string]$PackageRoot,[switch]$Preview,[switch]$SkipStartup) {
    $Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    Assert-NoReparse $Root
    $m=Read-Package $PackageRoot
    $prior=Read-Receipt $Root
    if ($prior) { Assert-ReceiptClean $Root $prior -CheckConfigs }
    $configs=[Collections.Generic.List[object]]::new()
    $previous=''
    if (!$SkipStartup) {
        foreach ($name in @('mcamxm.config','mcamx.config')) {
            $p=Join-Safe $ConfigDirectory $name
            if (!(Test-Path -LiteralPath $p -PathType Leaf)) { continue }
            $info=Read-Config $p
            $old=Get-StartupPath $info.Line
            $configs.Add([pscustomobject]@{info=$info;old=$old;newLine=(New-StartupLine $info.Line)})
        }
        if ($configs.Count -eq 0) { throw 'User config not found. Start Mastercam 2027 once, close it, then install; or use -SkipStartup for manual loading.' }
        $paths=@($configs | ForEach-Object old | Select-Object -Unique)
        if ($paths.Count -ne 1) { throw 'Metric and inch startup hooks differ. Use -SkipStartup and load MC2027SuiteStartup.dll manually, or unify the previous hooks.' }
        $previous=$paths[0]
        if ($prior) {
            if ($previous -ne $script:SuiteStartup) { throw 'The existing suite no longer owns the startup slot.' }
        }
        elseif ($previous -eq $script:SuiteStartup) { throw 'Startup points to this suite but its receipt is missing. Restore the previous configuration before reinstalling.' }
        elseif ($previous) { if (!(Test-Path -LiteralPath (Join-Safe $Root $previous) -PathType Leaf)) { throw "Previous startup DLL missing: $previous" } }
    }
    elseif ($prior -and @($prior.configs).Count -gt 0) { throw 'This installation already owns the startup slot; do not change to -SkipStartup during upgrade.' }
    $actions=[Collections.Generic.List[object]]::new(); $records=[Collections.Generic.List[object]]::new(); $oldRecords=@{}
    if ($prior) { foreach ($r in $prior.files) { $oldRecords[$r.path]=$r } }
    $payload=[Collections.Generic.List[object]]::new()
    foreach ($f in $m.files) { $payload.Add([pscustomobject]@{path=$f.path;bytes=[IO.File]::ReadAllBytes((Join-Safe (Join-Path $PackageRoot 'payload') $f.path))}) }
    $chain='chooks/MC2027SuitePrevious.ft'
    if ($prior -and $oldRecords.ContainsKey($chain)) { $payload.Add([pscustomobject]@{path=$chain;bytes=[IO.File]::ReadAllBytes((Join-Safe $Root $chain))}) }
    elseif (!$prior -and !$SkipStartup -and $previous) {
        if ($previous -match '["\r\n]') { throw 'Invalid previous hook path.' }
        $ft='APPLICATION "MC2027SuitePrevious"'+"`r`n"+'FUNC_DLL "'+$previous+'"'+"`r`n"+'RES_DLL "Workshop2027.Resources.dll", "chooks\Workshop2027"'+"`r`n"+'dnRES_NAME "Workshop2027.NETHook"'+"`r`n"+'CATEGORY "MC2027 Suite"'+"`r`n"+'FUNCTION NET "Run"'+"`r`n"+' FNAME "Previous startup"'+"`r`n"+'END_FUNCTION'+"`r`n"
        $payload.Add([pscustomobject]@{path=$chain;bytes=[Text.UTF8Encoding]::new($true).GetBytes($ft)})
    }
    elseif (Test-Path -LiteralPath (Join-Safe $Root $chain)) { throw 'An unmanaged MC2027SuitePrevious.ft already exists. Preserve/resolve it before installation.' }
    foreach ($f in $payload) {
        $record=[pscustomobject]@{path=$f.path;installedHash=$null;originalRecorded=$false;originalBackup=$null;originalHash=$null}
        if ($oldRecords.ContainsKey($f.path)) {
            $r=$oldRecords[$f.path];$record.originalRecorded=$true;$record.originalBackup=$r.originalBackup;$record.originalHash=$r.originalHash
            $oldRecords.Remove($f.path)
        }
        $a=New-Action (Join-Safe $Root $f.path) $f.bytes $record
        $record.installedHash=$a.hash;$records.Add($record);$actions.Add($a)
    }
    # Obsolete package files return to their pre-install state during upgrade.
    foreach ($r in $oldRecords.Values) {
        $b=$null
        if ($r.originalBackup) { $b=[IO.File]::ReadAllBytes((Join-Safe $Root $r.originalBackup)) }
        $actions.Add((New-Action (Join-Safe $Root $r.path) $b))
    }
    $configRecords=[Collections.Generic.List[object]]::new()
    foreach ($c in $configs) {
        $line=$c.info.Line
        if ($prior) {
            $match=@($prior.configs | Where-Object path -EQ $c.info.Path)
            if ($match.Count -ne 1) { throw 'Config scope changed; uninstall the previous scope before reinstalling.' }
            $line=$match[0].originalLine
        }
        $configRecords.Add([pscustomobject]@{path=$c.info.Path;originalLine=$line;installedLine=$c.newLine})
        $actions.Add((New-Action $c.info.Path (Config-Bytes $c.info $c.newLine)))
    }
    $receipt=[pscustomobject]@{schemaVersion=1;active=$true;root=$Root;version=$m.version;installedAt=(Get-Date).ToString('o');files=@($records.ToArray());configs=@($configRecords.ToArray())}
    if ($Preview) { return [pscustomobject]@{action='Preview';root=$Root;version=$m.version;files=$records.Count;startupConfigs=$configs.Count;previousStartup=$previous} }
    Invoke-FileTransaction $Root $actions (Join-Safe $Root 'chooks/.MC2027PluginSuite/receipt.json') $receipt
    Assert-ReceiptClean $Root $receipt -CheckConfigs
    return [pscustomobject]@{action='Installed';version=$m.version;files=$records.Count;root=$Root}
}
function Invoke-SuiteUninstall([string]$Root) {
    $Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    $r=Read-Receipt $Root
    if (!$r) { throw 'No active installation receipt found.' }
    Assert-ReceiptClean $Root $r -CheckConfigs
    $actions=[Collections.Generic.List[object]]::new()
    foreach ($f in $r.files) {
        $bytes=$null
        if ($f.originalBackup) { $bytes=[IO.File]::ReadAllBytes((Join-Safe $Root $f.originalBackup)) }
        $actions.Add((New-Action (Join-Safe $Root $f.path) $bytes))
    }
    foreach ($c in $r.configs) { $actions.Add((New-Action $c.path (Config-Bytes (Read-Config $c.path) $c.originalLine))) }
    $r.active=$false
    Invoke-FileTransaction $Root $actions (Join-Safe $Root 'chooks/.MC2027PluginSuite/receipt.json') $r
    return [pscustomobject]@{action='Uninstalled';restoredFiles=@($r.files).Count;backupsRetained=$true}
}
