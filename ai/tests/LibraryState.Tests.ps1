$ErrorActionPreference='Stop'
# Compile the exact production comparison method; Capture's native SDK reads are
# separately covered by the host harness. Only JSON serialization is supplied here.
$source=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../bridge/LibraryState.cs') -Raw
$method=$source.Substring($source.IndexOf('internal static void RequireEqual'))
$method=$method.Substring(0,$method.LastIndexOf('}'))
$prefix=@'
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
namespace MastercamPluginAI;
internal static class WorkshopBindings {internal static string Encode(object x)=>JsonSerializer.Serialize(x);}
internal static class LibraryState {
'@
$checks=@'
public static class LibraryStateChecks {
 public static int Run(string directory) {
  int count=0;
  string Base(double matrix=0,double origin=0,int pid=9,int tag=44,int id=7,string name="source",string faceType="Plane")=>JsonSerializer.Serialize(new{database=new{geometry=new[]{new{id,faces=new[]{new{Key=pid,Value=tag}}}},ops=new[]{new{name}},planes=new[]{new{ViewID=10,ViewOrigin=new{x=origin,y=0,z=0},ViewMatrix=new{Row1=new{x=1,y=matrix,z=0}}}}},solid_faces=new[]{new{id,faces=new[]{new{Pid=pid,Type=faceType}}}},groups=new[]{new{ID=1,Name="group"}}});
  void Check(string other,bool expected,string name){bool ok=true;try{LibraryState.RequireEqual(Base(),other,directory,name);}catch(InvalidOperationException){ok=false;}if(ok!=expected)throw new Exception(name);count++;}
  Check(Base(),true,"identical");
  Check(Base(matrix:1e-13),true,"unit-matrix-roundoff");
  Check(Base(matrix:1e-8),false,"real-matrix-edit");
  Check(Base(origin:1e-13),false,"origin-is-not-relaxed");
  Check(Base(tag:77),true,"temporary-face-retag");
  Check(Base(tag:77,pid:10),false,"persistent-face-change");
  Check(Base(tag:77,faceType:"Cylinder"),false,"retag-with-shape-change");
  Check(Base(id:8),false,"geometry-identity-change");
  Check(Base(name:"edited"),false,"operation-change");
  return count;
 }
}
'@
Add-Type -TypeDefinition ($prefix+"`n"+$method+"}`n"+$checks)
$out=Join-Path ([IO.Path]::GetTempPath()) ('MastercamLibraryStateTests-'+[guid]::NewGuid().ToString('N'))
$count=[MastercamPluginAI.LibraryStateChecks]::Run($out)
Write-Output "LibraryState: $count regression checks PASS; receipts=$out"
