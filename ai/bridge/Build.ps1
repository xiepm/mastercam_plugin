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
foreach($name in @('OperationTools2027','HSMRebuild2027','MPRebuild2027','PorscheAdvanced2027','AdvancedDrill2027')) {$paths+=Join-Path $repo ('payload\chooks\'+$name+'\'+$name+'.dll')}
$paths+=Join-Path $repo 'payload\chooks\MPRebuild2027\MPRebuild2027.Core.dll'
foreach($rel in @('MPEdgeTools2027/MPEdgeTools2027.dll','MPDesignTools2027/MPDesignTools2027.Core.dll','MPDesignTools2027/MPDesignTools2027.dll','MPDesignSurfaceSelect2027/MPDesignSurfaceSelect2027.Core.dll','MPDesignSurfaceSelect2027/MPDesignSurfaceSelect2027.dll','MPDesignRadiusSelect2027/MPDesignRadiusSelect2027.Core.dll','MPDesignRadiusSelect2027/MPDesignRadiusSelect2027.dll','GeometryTools2027/GeometryTools2027.dll','SVGGeometry2027/SVGGeometry2027.dll','TpSketcher2027/TpSketcher2027.Core.dll','TpSketcher2027/TpSketcher2027.dll','FixtureTools2027/FixtureTools2027.Core.dll','FixtureTools2027/FixtureTools2027.dll','HirthTools2027/HirthTools2027.Core.dll','HirthTools2027/HirthTools2027.dll','SetupSheets2027/SetupSheets2027.dll','LevelExport2027/LevelExport2027.Core.dll','LevelExport2027/LevelExport2027.dll','ScreenTools2027/ScreenTools2027.dll','ElectrodeReport2027/ElectrodeReport2027.Core.dll','ElectrodeReport2027/ElectrodeReport2027.dll')) {$paths+=Join-Path $repo ('payload/chooks/'+$rel)}
$paths+=Join-Path $repo 'payload/chooks/HolderTools2027/HolderTools2027.dll'
$paths+=Join-Path $MastercamRoot 'ToolNetApi.dll'
foreach($path in $paths){$refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile($path))}
$trees=[Microsoft.CodeAnalysis.SyntaxTree[]]@('PluginBridge.cs','PreviewGuard.cs','PorscheBindings.cs','GeometryBindings.cs','AttributeOnlyLevelExport.cs','UtilityBindings.cs','SketchHostAdapter.cs','SolidCopyAdapter.cs','SketchExecution.cs','RadiusHostAdapter.cs','PanelLauncher.cs' | ForEach-Object {[Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText((Join-Path $PSScriptRoot $_)))})
foreach($folder in @('EdgeAdapter','GeometryAdapter','FixtureAdapter')) { foreach($file in Get-ChildItem (Join-Path $PSScriptRoot $folder) -Filter '*.cs') {$trees += [Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText($file.FullName))} }
$options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary).WithPlatform([Microsoft.CodeAnalysis.Platform]::X64).WithDeterministic($true)
$assemblyName='MastercamPluginAI130'
$comp=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create($assemblyName,[Microsoft.CodeAnalysis.SyntaxTree[]]$trees,$refs,$options)
[void][IO.Directory]::CreateDirectory((Join-Path $PSScriptRoot 'bin'))
$out=Join-Path $PSScriptRoot ('bin\'+$assemblyName+'.dll')
$stream=[IO.File]::Create($out)
try{$result=$comp.Emit($stream)}finally{$stream.Dispose()}
$result.Diagnostics | ForEach-Object ToString
if(!$result.Success){throw 'AI bridge compilation failed'}
Get-FileHash -LiteralPath $out
$identity=[ordered]@{version='1.3.0.0';file=$assemblyName+'.dll';sha256=(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'identity.json'),($identity|ConvertTo-Json)+"`n",[Text.UTF8Encoding]::new($false))
