# Official CIMCO installer orchestration. Never copies or removes vendor DLLs directly.
function Get-CimcoSpec {
    return [pscustomobject]@{
        version='26.9.11.46240'
        name='CIMCO-Verify-26.9.11.46240.exe'
        url='https://downloads.mastercam.dk/dl/software/cimco/verify/CIMCO%20Verify%20for%20Mastercam%20(v26.9.11.46240).exe'
        bytes=43230352L
        sha256='0925229394EFCBA51E0B14F59456F2CADDC18128971F3F4BC039F9F8DA40E72E'
        files=@(
            @{path='chooks/CIMCOSimulation.dll';sha256='EDBD4CA0B22AA5CDCBB7AC5AD426F88F7826B00C462A7679F4EACB7679C69060'},
            @{path='chooks/CIMCOSimulation.ft';sha256='538B9F887481F08C4684E71E9E4E5FF0E25D393673980126F325B6F037960D1C'},
            @{path='LatheBarStock.dll';sha256='8992D456F41275EC6ECC960DD466C6F31DE35614CF96E6D932B7E2198A626C23'}
        )
    }
}
function Test-CimcoSignature([string]$Path) {
    $sig=Get-AuthenticodeSignature -LiteralPath $Path
    return ($sig.Status -eq 'Valid' -and $sig.SignerCertificate -and $sig.SignerCertificate.Subject -match '(?:^|,\s*)O=CIMCO A/S(?:,|$)')
}
function Get-CimcoRegistration {
    $items=@(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
        Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'CIMCO Verify for Mastercam' })
    if ($items.Count -gt 1) { throw 'Multiple CIMCO Verify registrations. Resolve them with the official installer first.' }
    if ($items.Count) { return $items[0] }
    return $null
}
function Get-CimcoState([string]$MastercamRoot) {
    $spec=Get-CimcoSpec
    $reg=Get-CimcoRegistration
    $present=@($spec.files | Where-Object { Test-Path -LiteralPath (Join-Safe $MastercamRoot $_.path) -PathType Leaf })
    $version=$null
    if ($reg -and $reg.PSObject.Properties['DisplayVersion']) { [void][version]::TryParse($reg.DisplayVersion,[ref]$version) }
    $sharedOK=$reg -and $reg.PSObject.Properties['InstallLocation'] -and $reg.InstallLocation -and (Test-Path -LiteralPath $reg.InstallLocation -PathType Container)
    if ($sharedOK) {
        foreach ($name in @('CIMCOSimulation.exe','SimulationWindow.dll','Msg/License.txt')) {
            if (!(Test-Path -LiteralPath (Join-Safe $reg.InstallLocation $name) -PathType Leaf)) { $sharedOK=$false }
        }
    }
    $valid=$false
    if ($sharedOK -and $version -and $version -ge [version]$spec.version -and $present.Count -eq $spec.files.Count) {
        $valid=Test-CimcoSignature (Join-Safe $MastercamRoot 'chooks/CIMCOSimulation.dll')
        $valid=$valid -and (Test-CimcoSignature (Join-Safe $MastercamRoot 'LatheBarStock.dll'))
        if ($version -eq [version]$spec.version) {
            foreach ($f in $spec.files) { if ((Get-Sha (Join-Safe $MastercamRoot $f.path)) -ne $f.sha256) { $valid=$false } }
        }
    }
    if ($valid) { return [pscustomobject]@{state='AlreadyInstalled';version=$version.ToString();action='Skip';reason='Compatible signed CIMCO installation found.'} }
    # Avoid downgrading a newer shared CIMCO product or silently repairing a modified installation.
    if ($version -and $version -gt [version]$spec.version) {
        return [pscustomobject]@{state='NeedsOfficialRepair';version=$version.ToString();action='Stop';reason='Newer CIMCO is installed but the selected Mastercam integration is incomplete. Repair with that version of the official installer.'}
    }
    if ($present.Count -gt 0 -and (!$version -or $version -ge [version]$spec.version)) {
        return [pscustomobject]@{state='NeedsOfficialRepair';version=if($version){$version.ToString()}else{$null};action='Stop';reason='Existing CIMCO files do not match a complete verified installation. Use the official repair installer; files were preserved.'}
    }
    return [pscustomobject]@{state=if($reg){'UpgradeRequired'}else{'NotInstalled'};version=if($version){$version.ToString()}else{$null};action='Install';reason='Official CIMCO Verify installer required.'}
}
function Assert-CimcoHostRegistration([string]$MastercamRoot) {
    $paths=@(@(foreach ($key in @('HKLM:\SOFTWARE\CNC Software\Mastercam 2027','HKLM:\SOFTWARE\CNC Software, Inc.\Mastercam 2027')) {
        $reg=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        if ($reg -and $reg.PSObject.Properties['Directory'] -and $reg.Directory) { [IO.Path]::GetFullPath($reg.Directory).TrimEnd('\') }
    }) | Select-Object -Unique)
    if (@($paths).Count -ne 1 -or $paths[0] -ne [IO.Path]::GetFullPath($MastercamRoot).TrimEnd('\')) {
        throw 'CIMCO installs to the registered Mastercam 2027 directory. The selected folder must match that registration.'
    }
}
function Assert-CimcoInstaller([string]$Path) {
    $spec=Get-CimcoSpec
    Assert-NoReparse $Path
    if (!(Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).Length -ne $spec.bytes -or (Get-Sha $Path) -ne $spec.sha256) { throw 'CIMCO installer SHA256/size mismatch; nothing was executed.' }
    if (!(Test-CimcoSignature $Path)) { throw 'CIMCO installer signature is not valid for CIMCO A/S; nothing was executed.' }
}
function Receive-CimcoChunks([string]$Curl,$Spec,[string]$Destination) {
    # Small ranged requests tolerate the vendor CDN's slow full-file responses.
    # Verify each length and the complete pinned SHA256 before anything is run.
    $chunkSize=1048576L
    $parts=[Collections.Generic.List[string]]::new()
    $jobs=[Collections.Generic.List[object]]::new()
    $next=0L; $completed=0
    try {
        while ($next -lt $Spec.bytes -or $jobs.Count -gt 0) {
            while ($next -lt $Spec.bytes -and $jobs.Count -lt 4) {
                $end=[Math]::Min($next+$chunkSize-1,$Spec.bytes-1)
                $part=$Destination+'.part'+$parts.Count.ToString('D3');$parts.Add($part)
                $job=Start-Job -ScriptBlock {
                    param($exe,$url,$first,$last,$out)
                    & $exe --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --retry 2 --connect-timeout 20 --max-time 180 --range ($first.ToString()+'-'+$last.ToString()) --user-agent 'Mozilla/5.0' --referer 'https://www.cimcoverify.com/' --output $out $url
                    if ($LASTEXITCODE -ne 0) { throw "CIMCO range download failed (curl $LASTEXITCODE)." }
                    if ((Get-Item -LiteralPath $out).Length -ne ($last-$first+1)) { throw 'CIMCO range length mismatch.' }
                } -ArgumentList $Curl,$Spec.url,$next,$end,$part
                $jobs.Add($job);$next=$end+1
            }
            $finished=Wait-Job -Job $jobs.ToArray() -Any -Timeout 10
            if ($finished) {
                Receive-Job -Job $finished -ErrorAction Stop | Out-Null
                if ($finished.State -ne 'Completed') { throw 'CIMCO range download did not complete.' }
                [void]$jobs.Remove($finished);Remove-Job -Job $finished;$completed++
                Write-Host ("CIMCO download: {0}/{1} chunks" -f $completed,[Math]::Ceiling($Spec.bytes/$chunkSize))
            }
        }
        $stream=[IO.File]::Create($Destination)
        try { foreach ($part in $parts) { $partStream=[IO.File]::OpenRead($part);try{$partStream.CopyTo($stream)}finally{$partStream.Dispose()} } }
        finally { $stream.Dispose() }
    } finally {
        foreach ($job in $jobs) { Stop-Job -Job $job -ErrorAction SilentlyContinue;Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
        foreach ($part in $parts) { if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force } }
    }
}
function Get-CimcoInstaller([string]$CacheDirectory) {
    $spec=Get-CimcoSpec
    $destination=Join-Safe $CacheDirectory $spec.name
    if (Test-Path -LiteralPath $destination) { Assert-CimcoInstaller $destination; return $destination }
    [void][IO.Directory]::CreateDirectory($CacheDirectory)
    $temp=Join-Safe $CacheDirectory ($spec.name+'.'+[guid]::NewGuid().ToString('N')+'.download')
    $oldProtocol=[Net.ServicePointManager]::SecurityProtocol
    try {
        [Net.ServicePointManager]::SecurityProtocol=$oldProtocol -bor [Net.SecurityProtocolType]::Tls12
        Write-Host 'Downloading CIMCO Verify from the official server (about 43 MB)...'
        $curl=Join-Path $env:SystemRoot 'System32\curl.exe'
        if (Test-Path -LiteralPath $curl -PathType Leaf) {
            Receive-CimcoChunks $curl $spec $temp
        } else {
            Invoke-WebRequest -Uri $spec.url -OutFile $temp -UseBasicParsing -TimeoutSec 300 -UserAgent 'Mozilla/5.0 MastercamPluginSuite/2027' -Headers @{Referer='https://www.cimcoverify.com/'}
        }
        Assert-CimcoInstaller $temp
        Move-Item -LiteralPath $temp -Destination $destination
        return $destination
    }
    finally {
        [Net.ServicePointManager]::SecurityProtocol=$oldProtocol
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}
function Get-CimcoArguments([string]$LogPath) {
    if ($LogPath -match '["\r\n]') { throw 'Unsupported log path characters.' }
    return '/VERYSILENT /SP- /TYPE=custom /COMPONENTS="general,mcam\v27" /LANG=en /NORESTART /RESTARTEXITCODE=3010 /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /LOG="'+$LogPath+'"'
}
function Invoke-CimcoInstall([string]$MastercamRoot,[string]$Installer,[string]$ReportDirectory) {
    [void][IO.Directory]::CreateDirectory($ReportDirectory)
    $reportPath=Join-Safe $ReportDirectory 'cimco-result.json'
    $before=Get-CimcoState $MastercamRoot
    if ($before.action -eq 'Skip') {
        $result=[ordered]@{component='CIMCO Verify';state='AlreadyInstalled';version=$before.version;changed=$false;restartRequired=$false;validation='Registration, file presence and signatures; native UI was not run.'}
        Write-Json $reportPath $result
        return [pscustomobject]$result
    }
    if ($before.action -eq 'Stop') { throw $before.reason }
    Assert-CimcoHostRegistration $MastercamRoot
    Assert-CimcoInstaller $Installer
    if (Get-Process -Name Mastercam -ErrorAction SilentlyContinue) { throw 'Close Mastercam normally before CIMCO installation.' }
    $logPath=Join-Safe $ReportDirectory ('cimco-install-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
    $result=[ordered]@{component='CIMCO Verify';state='Installing';version=(Get-CimcoSpec).version;changed=$true;exitCode=$null;restartRequired=$false;log=$logPath;validation='Not yet verified.'}
    Write-Json $reportPath $result
    try {
        Write-Host 'Installing official CIMCO Verify integration for Mastercam 2027...'
        $p=Start-Process -FilePath $Installer -ArgumentList (Get-CimcoArguments $logPath) -WindowStyle Hidden -Wait -PassThru
        $result.exitCode=$p.ExitCode
        if ($p.ExitCode -notin @(0,3010)) { throw "CIMCO installer failed with code $($p.ExitCode). See $logPath" }
        $result.restartRequired=$p.ExitCode -eq 3010
        if ($result.restartRequired) {
            $result.state='RestartRequired';$result.validation='Official installer requested restart. Re-run Install.cmd after reboot for file verification.'
        } else {
            $after=Get-CimcoState $MastercamRoot
            if ($after.action -ne 'Skip') { throw 'CIMCO installer exited but integration verification failed. See the official installer log.' }
            $result.state='Installed';$result.validation='Registration, file presence and signatures; native UI was not run.'
        }
        Write-Json $reportPath $result
        return [pscustomobject]$result
    } catch {
        $result.state='Failed';$result.validation=$_.Exception.Message;Write-Json $reportPath $result
        throw 'CIMCO installation did not complete. The core plugin suite remains installed. Repair CIMCO with its official installer or retry Install.cmd. '+$_.Exception.Message
    }
}
