#r "__SYSTEM_TEXT_JSON__"
using System;using System.IO;using System.Linq;using System.Reflection;using System.Collections;using System.Collections.Generic;using System.Text.Json;
using Mastercam.Support;using Mastercam.IO;using Mastercam.Operations;using Mastercam.Database;using Mastercam.Math;
new ConfigRead().Run(__MODEL__,__RECEIPT__);
public class ConfigRead{
 static Dictionary<string,object> D(params object[] pairs){var d=new Dictionary<string,object>();for(int i=0;i<pairs.Length;i+=2)d[(string)pairs[i]]=pairs[i+1];return d;}
 static object Read(object obj,int depth){
  if(obj==null)return null;var t=obj.GetType();
  if(t.IsEnum)return obj.ToString();if(t.IsPrimitive||obj is string||obj is decimal)return obj;
  if(obj is DateTime)return ((DateTime)obj).ToString("O");
  if(obj is Point3D){var p=(Point3D)obj;return new[]{p.x,p.y,p.z};}
  if(obj is MCView){var v=(MCView)obj;return D("id",v.ViewID,"name",v.ViewName,"origin",Read(v.ViewOrigin,0),"x",Read(v.ViewMatrix.Row1,0),"y",Read(v.ViewMatrix.Row2,0),"z",Read(v.ViewMatrix.Row3,0),"work_offset",v.WorkOffsetNumber);}
  if(depth<0)return D("unexpanded_type",t.FullName);
  if(obj is IEnumerable){var list=new List<object>();foreach(var x in (IEnumerable)obj){if(list.Count>=100){list.Add(D("truncated",true));break;}list.Add(Read(x,depth-1));}return list;}
  var data=D("_type",t.FullName);
  foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance).Where(p=>p.CanRead&&p.GetIndexParameters().Length==0))try{data[p.Name]=Read(p.GetValue(obj),depth-1);}catch(Exception e){data[p.Name]=D("read_error",e.GetBaseException().Message);}
  foreach(var f in t.GetFields(BindingFlags.Public|BindingFlags.Instance))try{data[f.Name]=Read(f.GetValue(obj),depth-1);}catch(Exception e){data[f.Name]=D("read_error",e.GetBaseException().Message);}
  return data;
 }
 public void Run(string model,string receipt){
  var r=D("schema_version","aicnc.mastercam.configuration-readback/0.1","ok",false,"pid",Environment.ProcessId,"utc",DateTime.UtcNow.ToString("O"),"production_released",false);
  try{
   if(File.Exists(receipt))throw new Exception("Receipt exists");
   if(!Path.GetFullPath(FileManager.CurrentFileName).Equals(Path.GetFullPath(model),StringComparison.OrdinalIgnoreCase))throw new Exception("Wrong document");
   r["model"]=FileManager.CurrentFileName;r["model_sha256"]=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(model))).ToLowerInvariant();
   r["api_version"]=typeof(Operation).Assembly.FullName;r["metric"]=SettingsManager.Metric;
   r["machine_name"]=MachineDefManager.GetCurrentMachineName();r["post_name"]=OperationsManager.PostName;r["material"]=OperationsManager.JobSetupMaterial;r["stock"]=Read(MillStock.GetStockData(),2);
   var rows=new List<object>();
   foreach(var o in SearchManager.GetOperations()){
    var e=OperationsManager.GetOperationExtents(o.GetOperationID());
    rows.Add(D("cam_operation_id",o.GetOperationID(),"name",o.Name,"group_id",o.GroupNumber,"group_name",GroupManager.FindGroupByID(o.GroupNumber).Name,"type",o.GetType().FullName,"parameters",Read(o,3),"linking",Read(o.Linking,2),"home",Read(o.HomePosition,2),"reference_points",Read(o.ReferencePoints,2),"tool",Read(o.OperationTool,2),"chains",o is ChainBasedOperation?Read(((ChainBasedOperation)o).GetChainArray(),2):null,"extents",Read(e,2),"cycle_seconds",o.CalcCycleTime()));
   }
   r["operations"]=rows;
   var sheets=new List<object>();for(int i=0;i<ViewSheets.GetSheetCount();i++){var d=new ViewSheets.ViewSheetData();if(!ViewSheets.GetViewSheetData(i,ref d))throw new Exception("View sheet read failed");sheets.Add(D("index",i,"name",ViewSheets.GetViewSheetName(i),"wcs_id",d.WcsPlaneID,"tool_plane_id",d.ToolPlaneID,"construction_plane_id",d.ConstructionPlaneID,"graphics_plane_id",d.GraphicsPlaneID));}r["view_sheets"]=sheets;
   var methods=new List<string>();foreach(var m in typeof(OperationsManager).GetMethods(BindingFlags.Public|BindingFlags.Static).Where(m=>m.Name.Contains("NCI")||m.Name.Contains("Toolpath")||m.Name.Contains("Export")))methods.Add(m.ToString());r["motion_api_methods"]=methods;
   r["ok"]=true;
  }catch(Exception e){r["error"]=e.ToString();}
  File.WriteAllText(receipt,JsonSerializer.Serialize(r,new JsonSerializerOptions{WriteIndented=true}));
 }
}
