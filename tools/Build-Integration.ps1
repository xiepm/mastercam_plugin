param([Parameter(Mandatory=$true)][string]$MastercamRoot)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Build requires PowerShell 7 with Roslyn.' }
$root = Split-Path $PSScriptRoot -Parent
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.CSharp.dll')
$shared = Join-Path $env:ProgramFiles 'dotnet\shared'
$references = [Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach ($framework in @('Microsoft.NETCore.App','Microsoft.WindowsDesktop.App')) {
    $runtime = Get-ChildItem (Join-Path $shared $framework) -Directory | Where-Object Name -Match '^10\.\d+\.\d+$' | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
    if (!$runtime) { throw "Missing .NET 10 runtime: $framework" }
    foreach ($file in Get-ChildItem $runtime.FullName -Filter '*.dll') {
        try { [void][Reflection.AssemblyName]::GetAssemblyName($file.FullName); $references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($file.FullName)) } catch { }
    }
}
$api = Join-Path $MastercamRoot 'NETHook3_0.dll'
if ([Reflection.AssemblyName]::GetAssemblyName($api).Version.Major -ne 29) { throw 'API29 required.' }
$references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($api))
$options = [Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary).WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Release).WithDeterministic($true)
foreach ($item in @(@{Source='Workshop';Name='Workshop2027'},@{Source='Bootstrap';Name='MC2027SuiteStartup'})) {
    $trees = [Microsoft.CodeAnalysis.SyntaxTree[]]@(Get-ChildItem (Join-Path $root ('src\'+$item.Source)) -Filter '*.cs' | Sort-Object Name | ForEach-Object { [Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText($_.FullName),$null,$_.Name) })
    $comp = [Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create($item.Name,$trees,$references,$options)
    $destination = Join-Path $root ('payload\chooks\'+$item.Name)
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $stream = [IO.File]::Create((Join-Path $destination ($item.Name+'.dll')))
    try { $result = $comp.Emit($stream) } finally { $stream.Dispose() }
    if (!$result.Success) { throw ($result.Diagnostics -join "`n") }
    Write-Output ($item.Name + ': compile PASS')
}
