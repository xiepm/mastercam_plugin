#r "__SYSTEM_TEXT_JSON__"
using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Text.Json;
using Mastercam.Math;using Mastercam.Support;using Mastercam.IO;using Mastercam.Operations;
// Render only against a separately preserved/copied stand software trial.
// This reference point is not a production machine-home or toolchange position.
new StandReturnPoint().Run(__MODEL__,__MODEL_SHA__,__RECEIPT__,__CLEARANCE_MM__);
public sealed class StandReturnPoint {
 public void Run(string model,string expectedHash,string receipt,double requestedClearance){
  if(File.Exists(receipt))throw new Exception("Receipt already exists");
  if(requestedClearance!=5&&requestedClearance!=10)throw new Exception("Unsupported trial clearance");
  var rows=new List<object>();var result=new Dictionary<string,object>{{"ok",false},{"production_released",false},{"resource_status","simulation_only"},{"changes",rows},{"pid",Environment.ProcessId}};
  try{
   if(!Path.GetFullPath(FileManager.CurrentFileName).Equals(Path.GetFullPath(model),StringComparison.OrdinalIgnoreCase))throw new Exception("Document guard");
   var hash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(model))).ToLowerInvariant();if(hash!=expectedHash)throw new Exception("Source file changed");
   var all=SearchManager.GetOperations();if(!SettingsManager.Metric||!all.Select(o=>o.Name).SequenceEqual(new[]{"S1_external","S1_through","S1_top_chamfer","S2_counterbore","S2_blind_14","S2_blind_16","S2_blind_18","S2_blind_20","S2_bottom_chamfer"}))throw new Exception("Unsupported source profile");
   foreach(var id in all.Select(o=>o.GetOperationID()).ToArray()){
    var o=SearchManager.GetOperations().Single(o=>o.GetOperationID()==id);if(!o.Retrieve()||o.Dirty)throw new Exception("Invalid operation");
    var w=o.WCS;var l=o.Linking;bool top=o.Name.StartsWith("S1_");
    if(!l.ClearanceOn||l.ClearanceStartEndOnly||l.ClearanceIncremental||l.ClearanceAssociative||l.Clearance!=10||w.ViewOrigin.x!=0||w.ViewOrigin.y!=0||w.ViewOrigin.z!=(top?10:0)||w.ViewMatrix.Row3.x!=0||w.ViewMatrix.Row3.y!=0||w.ViewMatrix.Row3.z!=(top?1:-1))throw new Exception("Unsupported frame/height");
    var before=(Point3D)o.HomePosition.Point;var oldClearance=l.Clearance;
    // Explicit trial request. Do not move the WCS or machine zero.
    l.Clearance=requestedClearance;
    var p=new Point3D(0,0,w.ViewOrigin.z+requestedClearance*w.ViewMatrix.Row3.z);
    o.HomePosition.Point=p;o.HomePosition.Enabled=true;
    if(!o.Commit()||!o.Regenerate()||!o.Retrieve()||o.Dirty)throw new Exception("Write/regenerate/readback failed");
    var after=(Point3D)o.HomePosition.Point;if(!o.HomePosition.Enabled||after.x!=p.x||after.y!=p.y||after.z!=p.z||o.Linking.Clearance!=requestedClearance)throw new Exception("Readback mismatch");
    rows.Add(new{id,name=o.Name,before=new[]{before.x,before.y,before.z},after=new[]{after.x,after.y,after.z},clearance_before_mm=oldClearance,clearance_after_mm=o.Linking.Clearance,local_return_point_mm=new[]{0.0,0.0,requestedClearance},regenerated=true,readback_verified=true});
   }
   if(!FileManager.Save())throw new Exception("Save failed");OperationsManager.InitOperationsManagerTree();result["ok"]=true;result["model"]=FileManager.CurrentFileName;
  }catch(Exception e){result["error"]=e.ToString();}
  using(var output=new FileStream(receipt,FileMode.CreateNew,FileAccess.Write))JsonSerializer.Serialize(output,result,new JsonSerializerOptions{WriteIndented=true});
 }
}
