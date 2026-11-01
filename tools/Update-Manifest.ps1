param([string]$Version='2027.11.01.1')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$payload=Join-Path $root 'payload'
$files=@(Get-ChildItem -LiteralPath $payload -File -Recurse | Sort-Object FullName | ForEach-Object {
    $relative=$_.FullName.Substring($payload.Length+1).Replace('\','/')
    $assemblyVersion=$null; $nativeVersion=$null
    if ($_.Extension -eq '.dll') {
        try { $assemblyVersion=[Reflection.AssemblyName]::GetAssemblyName($_.FullName).Version.ToString() }
        catch [System.BadImageFormatException] { $nativeVersion=$null }
    }
    if ($_.Extension -eq '.dll' -and !$assemblyVersion) { $nativeVersion=$_.VersionInfo.FileVersion }
    [ordered]@{path=$relative;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash;assemblyVersion=$assemblyVersion;nativeFileVersion=$nativeVersion}
})
$native=@(
    [ordered]@{path='NETHook3_0.dll';sha256='A5F87967FB5E8CFB7EA2A66CF984C9F0E468FE67B0CB0AF5A7B334CF50D404FF'},
    [ordered]@{path='MCCORE.dll';sha256='0F9C445215D93A7A3C5C25337134BB1E2CB5884642EA0B736EC5BEBF403ED14E'},
    [ordered]@{path='MCGeomSld.dll';sha256='C73D6C39B110EC708D0989650DAFB8E1AA778D57B86ED8ED4ABADED263B85038'},
    [ordered]@{path='PSKERNEL.dll';sha256='44B9A90D60DB1ED231D171EBAD1BC68EED79B39DFB2088D8E3B341E57FD148A5'},
    [ordered]@{path='chooks/MCNetScripting/IPCServer.dll';sha256='8FE0F6EAED60FB0628E570557D4906937660953D0FBAB719818B8F0FDAFEF6BD'}
)
$moduleCount=(Get-Content -LiteralPath (Join-Path $root 'catalog\modules.json') -Raw | ConvertFrom-Json).Count
$value=[ordered]@{schemaVersion=1;version=$Version;mastercam='2027';api=29;platform='windows-x64';runtime='.NET 10 Windows Desktop';moduleCount=$moduleCount;nativeBuild=$native;files=$files}
[IO.File]::WriteAllText((Join-Path $root 'catalog\package.json'),($value|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output ("Manifest: {0} files, {1} bytes" -f $files.Count,($files|ForEach-Object { $_.bytes }|Measure-Object -Sum).Sum)
