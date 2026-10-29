param([string]$MastercamRoot=(Join-Path $env:ProgramFiles 'Mastercam 2027'))
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.CSharp.dll')
$refs=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach($framework in @('Microsoft.NETCore.App','Microsoft.WindowsDesktop.App')) {
 $runtime=Get-ChildItem (Join-Path $env:ProgramFiles ('dotnet\shared\'+$framework)) -Directory | Where-Object Name -match '^10\.\d+\.\d+$' | Sort-Object {[version]$_.Name} -Descending | Select-Object -First 1
 foreach($f in Get-ChildItem $runtime.FullName -Filter '*.dll') {try{[void][Reflection.AssemblyName]::GetAssemblyName($f.FullName);$refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($f.FullName))}catch{}}
}
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$paths=@((Join-Path $MastercamRoot 'NETHook3_0.dll'))
foreach($name in @('OperationTools2027','HSMRebuild2027','MPRebuild2027','PorscheAdvanced2027')) {$paths+=Join-Path $repo ('payload\chooks\'+$name+'\'+$name+'.dll')}
$paths+=Join-Path $repo 'payload\chooks\MPRebuild2027\MPRebuild2027.Core.dll'
foreach($path in $paths){$refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($path))}
$trees=[Microsoft.CodeAnalysis.SyntaxTree[]]@('PluginBridge.cs','PreviewGuard.cs' | ForEach-Object {[Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText((Join-Path $PSScriptRoot $_)))})
$options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary).WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).WithDeterministic($true)
$assemblyName='MastercamPluginAI102'
$comp=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create($assemblyName,$trees,$refs,$options)
[void][IO.Directory]::CreateDirectory((Join-Path $PSScriptRoot 'bin'))
$out=Join-Path $PSScriptRoot ('bin\'+$assemblyName+'.dll')
$stream=[IO.File]::Create($out)
try{$result=$comp.Emit($stream)}finally{$stream.Dispose()}
$result.Diagnostics | ForEach-Object ToString
if(!$result.Success){throw 'AI bridge compilation failed'}
Get-FileHash -LiteralPath $out
$identity=[ordered]@{version='1.0.2.0';file=$assemblyName+'.dll';sha256=(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'identity.json'),($identity|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
