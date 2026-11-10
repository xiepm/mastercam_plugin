#requires -Version 7.0
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$taskWork=Join-Path $repo ('.test-work/dependencies-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($taskWork)
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.dll')
Add-Type -Path (Join-Path $PSHOME 'Microsoft.CodeAnalysis.CSharp.dll')
$runtime=Get-ChildItem (Join-Path $env:ProgramFiles 'dotnet/shared/Microsoft.NETCore.App') -Directory | Where-Object Name -Match '^10\.\d+\.\d+$'|Sort-Object {[version]$_.Name} -Descending|Select-Object -First 1
$refs=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
foreach($f in Get-ChildItem -LiteralPath $runtime.FullName -Filter '*.dll') {try{[void][Reflection.AssemblyName]::GetAssemblyName($f.FullName);$refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($f.FullName))}catch{}}
function Compile([string]$Name,[string[]]$Code,[string]$Path,[string[]]$Extra=@(),[switch]$Exe){
 [void][IO.Directory]::CreateDirectory((Split-Path $Path -Parent))
 $r=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new($refs)
 foreach($p in $Extra){$r.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($p))}
 $trees=[Microsoft.CodeAnalysis.SyntaxTree[]]@($Code|ForEach-Object{[Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText($_)})
 $kind=if($Exe){[Microsoft.CodeAnalysis.OutputKind]::ConsoleApplication}else{[Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary}
 $options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new($kind)
 $comp=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create($Name,$trees,$r,$options)
 $stream=[IO.File]::Create($Path)
 try{$result=$comp.Emit($stream)}finally{$stream.Dispose()}
 if(!$result.Success){throw ($result.Diagnostics -join [Environment]::NewLine)}
}
$template=Join-Path $taskWork 'template with spaces/chooks'
$ad=Join-Path $template 'AdvancedDrill2027/AdvancedDrill2027.dll'
$op=Join-Path $template 'OperationTools2027/OperationTools2027.dll'
$po=Join-Path $template 'PorscheAdvanced2027/PorscheAdvanced2027.dll'
Compile 'AdvancedDrill2027' @('[assembly:System.Reflection.AssemblyVersion("0.1.2.0")] public class DrillBase {}') $ad
Compile 'OperationTools2027' @('[assembly:System.Reflection.AssemblyVersion("1.0.3.0")] public class OperationBase {}') $op
Compile 'PorscheAdvanced2027' @('[assembly:System.Reflection.AssemblyVersion("1.0.0.0")] public class PorscheDrill:DrillBase {} public class PorscheOperation:OperationBase {}') $po @($ad,$op)
Compile 'MPRebuild2027' @('public class MP:PorscheDrill {}') (Join-Path $template 'MPRebuild2027/MPRebuild2027.dll') @($po,$ad)
Compile 'AdvancedDrill2027' @('[assembly:System.Reflection.AssemblyVersion("0.1.1.0")] public class DrillBase {}') (Join-Path $template 'wrong/AdvancedDrill2027.dll')
[void][IO.Directory]::CreateDirectory((Join-Path $template 'other'))
Copy-Item -LiteralPath $ad -Destination (Join-Path $template 'other/AdvancedDrill2027.dll')
$runner=Join-Path $template 'MC2027SuiteStartup/DependencyRunner.dll'
Compile 'DependencyRunner' @([IO.File]::ReadAllText((Join-Path $repo 'src/Shared/PluginDependencies.cs')),[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'DependencyResolution.Tests.cs'))) $runner -Exe
[IO.File]::WriteAllText([IO.Path]::ChangeExtension($runner,'.runtimeconfig.json'),'{"runtimeOptions":{"tfm":"net10.0","framework":{"name":"Microsoft.NETCore.App","version":"10.0.0"}}}')
$checks=@(foreach($scenario in @('cold-resolve','forward-transitive','missing-file','wrong-file-version','loaded-other-location','requested-other-version','unknown-not-intercepted','unrelated-command')) {
 $caseRoot=Join-Path $taskWork $scenario
 Copy-Item -LiteralPath (Split-Path $template -Parent) -Destination $caseRoot -Recurse
 $output=& dotnet (Join-Path $caseRoot 'chooks/MC2027SuiteStartup/DependencyRunner.dll') $scenario 2>&1
 if($LASTEXITCODE -ne 0){throw ($output -join [Environment]::NewLine)}
 [pscustomobject]@{scenario=$scenario;passed=$true}
})
[pscustomobject]@{passed=$true;scenarios=$checks;scope='Isolated .NET 10 processes with synthetic cross-module assemblies; not a Mastercam machining test.'}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $repo 'validation/dependency-loader-tests.json') -Encoding utf8
$checks|Format-Table -AutoSize
