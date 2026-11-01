#r "__SYSTEM_TEXT_JSON__"
using System;using System.IO;using System.Linq;using System.Collections.Generic;using System.Text.Json;
using Mastercam.Database;using Mastercam.Math;using Mastercam.Support;using Mastercam.IO;using Mastercam.Operations;
new StandSetups().Run(__ROOT__,__MODE__,__RECEIPT__);
public sealed class StandSetups {
 static void Need(bool value,string why){if(!value)throw new Exception(why);}
 static object V(Point3D p){return new[]{p.x,p.y,p.z};}
 static string Hash(string p){return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();}
 static Dictionary<string,object> O(params object[] a){var d=new Dictionary<string,object>();for(int i=0;i<a.Length;i+=2)d[(string)a[i]]=a[i+1];return d;}
 static object PlaneRead(MCView v){return O("id",v.ViewID,"name",v.ViewName,"origin",V(v.ViewOrigin),"x",V(v.ViewMatrix.Row1),"y",V(v.ViewMatrix.Row2),"z",V(v.ViewMatrix.Row3),"work_offset",v.WorkOffsetNumber);}
 static MCView Plane(string name,bool bottom){
  Need(!ViewManager.GetAllViews(true).Any(v=>v.ViewName==name),"plane already exists");
  var v=new MCView();Need(v.Commit(),"initialize plane");v.ViewName=name;
  v.ViewOrigin=new Point3D(0,0,bottom?0:10);
  v.ViewMatrix=new Matrix3D(new Point3D(1,0,0),new Point3D(0,bottom?-1:1,0),new Point3D(0,0,bottom?-1:1));
  v.WorkOffsetNumber=(short)(bottom?1:0);Need(v.Commit(),"commit plane");Need(v.Retrieve(),"read plane");return v;
 }
 static void Activate(MCView v){ViewManager.WorkCoordinateSystem=v;ViewManager.CPlane=v;ViewManager.TPlane=v;ViewManager.GraphicsView=v;GraphicsManager.FitScreen();}
 static int Sheet(string name,MCView view){
  Activate(view);Need(ViewSheets.CreateViewSheet(name),"create sheet "+name);int i=ViewSheets.GetViewSheet(name);Need(i>=0,"sheet index");Need(ViewSheets.SetActiveViewSheet(i),"activate sheet");Activate(view);
  var d=new ViewSheets.ViewSheetData();Need(ViewSheets.GetViewSheetData(i,ref d),"read sheet");
  d.WcsPlaneID=view.ViewID;d.GraphicsPlaneID=view.ViewID;d.ToolPlaneID=view.ViewID;d.ConstructionPlaneID=view.ViewID;
  d.WcsPlaneMatrix=view.ViewMatrix;d.GraphicsPlaneMatrix=view.ViewMatrix;d.ToolPlaneMatrix=view.ViewMatrix;d.ConstructionPlaneMatrix=view.ViewMatrix;
  Need(ViewSheets.SetViewSheetData(i,d),"write sheet");Need(ViewSheets.SaveBookmark(i),"save sheet bookmark");return i;
 }
 public void Run(string root,string mode,string receipt){
  var r=O("ok",false,"mode",mode,"pid",Environment.ProcessId,"production_released",false);string stage="preflight";
  try{
   Need(!File.Exists(receipt),"receipt exists");Need(SettingsManager.Metric,"metric required");
   string original=@"D:\AICNC\测试工件\Mastercam2027_加工结果\stand-2setup.mcam";
   string expectedOriginal="be7783a6f226cf735b6164af0a1534b2c3ed0b336a79ea8caaea2cf7ec84a1e6";
   string machineDefinition=@"C:\Users\Public\Documents\Shared Mastercam 2027\CNC_Machines\MILL 3 - AXIS VMC MM.mcam-mmd";
   // A fresh replay binds the newly generated source, never an old delivered MCAM.
   string replayRequest=Path.Combine(root,"setup-replay.json");
   if(File.Exists(replayRequest)){
    var request=JsonDocument.Parse(File.ReadAllText(replayRequest)).RootElement;
    Need(request.GetProperty("schema_version").GetString()=="aicnc.mastercam-setup-replay-request/0.1","replay request version");
    original=Path.GetFullPath(request.GetProperty("source_model").GetString());
    Need(original.Equals(Path.GetFullPath(Path.Combine(root,"stand-2setup.mcam")),StringComparison.OrdinalIgnoreCase),"replay source scope");
    expectedOriginal=request.GetProperty("source_model_sha256").GetString();
    machineDefinition=Path.GetFullPath(request.GetProperty("machine_definition").GetString());
    Need(Hash(original)==expectedOriginal&&Hash(machineDefinition)==request.GetProperty("machine_sha256").GetString(),"replay source/machine changed");
    Need(Hash(Path.Combine(root,"source.step"))=="68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429","replay STEP identity");
   }
   string output=Path.GetFullPath(root+"/stand-3axis-2setups.mcam");
   var ops=SearchManager.GetOperations();Need(ops.Length==9&&ops.Select(o=>o.Name).SequenceEqual(new[]{"S1_external","S1_through","S1_top_chamfer","S2_counterbore","S2_blind_14","S2_blind_16","S2_blind_18","S2_blind_20","S2_bottom_chamfer"}),"source operations changed");
   if(mode=="apply"){
    Need(string.Equals(Path.GetFullPath(FileManager.CurrentFileName),Path.GetFullPath(original),StringComparison.OrdinalIgnoreCase),"wrong source");
    Need(Hash(original)==expectedOriginal,"source model hash changed");
    Need(ops.All(o=>!o.Dirty&&o.GroupNumber==2),"unexpected source state");Need(!File.Exists(output)&&!File.Exists(root+"/before-current-session.mcam"),"output exists");
    stage="preserve session";string snapshot=Path.GetFullPath(root+"/before-current-session.mcam");Need(FileManager.SaveAs(snapshot,false),"snapshot save");
    FileManager.CurrentFileName=snapshot;Need(FileManager.Save(),"snapshot filename");
    Need(FileManager.SaveAs(output,false),"working save");FileManager.CurrentFileName=output;Need(FileManager.Save(),"working filename");
    stage="groups and WCS";
    var top=Plane("S1_TOP_G54",false);var bottom=Plane("S2_FLIP_G55",true);
    var first=GroupManager.FindGroupByID(2);var machine=first.GetParentGroup();Need(machine.IsMachineGroup(),"machine group");
    Need(GroupManager.SetMachineInGroup(machine,machineDefinition),"3-axis machine definition");
    first.Name="装夹1_正面_3道";var second=GroupManager.NewGroup(machine,"装夹2_翻面_6道");Need(second!=null&&second.IsToolpathGroup(),"second toolpath group");
    machine.Name="三轴铣削_两次手动装夹";
    var before=new List<object>();
    for(int i=0;i<ops.Length;i++){
     var o=ops[i];stage="operation "+o.Name;File.WriteAllText(receipt+".progress",stage);
     var ext=OperationsManager.GetOperationExtents(o.GetOperationID());before.Add(O("name",o.Name,"world_min",V(ext.WorldMin),"world_max",V(ext.WorldMax)));
     var plane=i<3?top:bottom;
     if(i>=3)Need(OperationsManager.MoveOperation(o,second),"move operation");
     Need(o.Retrieve(),"retrieve operation");o.GroupNumber=i<3?first.ID:second.ID;o.WCS=plane;o.ToolPlane=plane;o.ConstructionPlane=plane;o.UseWCS=true;o.UseToolPlane=true;o.UseConstructionPlane=true;
     // Linking heights are plane coordinates. Rebase S1 from world Z=0 to its top face Z=10.
     if(i<3){o.Linking.Clearance-=10;o.Linking.Retract-=10;o.Linking.FeedPlane-=10;o.Linking.TopStock-=10;o.Linking.Depth-=10;}
     o.ProgramNumber=i<3?1001:1002;o.DisplayToolpath=false;
     Need(o.Commit(),"commit operation");Need(o.Regenerate(),"regenerate operation");Need(o.Retrieve()&&!o.Dirty,"clean path");
     var after=OperationsManager.GetOperationExtents(o.GetOperationID());
     Need(Math.Abs(after.WorldMin.x-ext.WorldMin.x)<1e-6&&Math.Abs(after.WorldMin.y-ext.WorldMin.y)<1e-6&&Math.Abs(after.WorldMin.z-ext.WorldMin.z)<1e-6&&Math.Abs(after.WorldMax.x-ext.WorldMax.x)<1e-6&&Math.Abs(after.WorldMax.y-ext.WorldMax.y)<1e-6&&Math.Abs(after.WorldMax.z-ext.WorldMax.z)<1e-6,"world toolpath extents changed: "+o.Name);
    }
    // Group insertion is at the head; reverse traversal preserves chronological order.
    foreach(var o in ops.Skip(3).Reverse())Need(OperationsManager.MoveOperation(o,second),"order second setup");
    r["before_extents"]=before;stage="setup view sheets";
    ViewSheets.ViewSheetsEnabled=true;var settings=new ViewSheets.ViewSheetSettings();Need(ViewSheets.GetSaveToViewSheetSettings(ref settings),"sheet settings");
    settings.WcsPlane=true;settings.ToolPlanes=true;settings.ConstructionPlanes=true;settings.GraphicsView=true;settings.AutoRestore=true;
    Need(ViewSheets.SetSaveToViewSheetSettings(settings),"save sheet settings");
    int firstSheet=Sheet("装夹1_正面_G54",top);int secondSheet=Sheet("装夹2_翻面_G55",bottom);
    // This bound source has one default sheet. Retain only the two setup sheets.
    Need(ViewSheets.GetSheetCount()==3&&firstSheet==1&&secondSheet==2,"unexpected source view sheets");
    Need(ViewSheets.DeleteViewSheet(0),"remove source default sheet");
    // Renaming a sheet to its existing name can fail the uniqueness check.
    // Assign distinct delivery labels; cold read still verifies persistence.
    string[] labels={"装夹1_正面_G54","装夹2_翻面_G55"};
    for(int i=0;i<labels.Length;i++)if(ViewSheets.GetViewSheetName(i)!=labels[i])Need(ViewSheets.RenameViewSheet(i,labels[i]),"rename setup sheet");
    firstSheet=ViewSheets.GetViewSheet(labels[0]);Need(firstSheet==0,"valid setup1 sheet index");
    Need(ViewSheets.SetActiveViewSheet(firstSheet),"restore setup1");Activate(top);Need(ViewSheets.SaveBookmark(firstSheet),"bookmark setup1");
    Need(GroupManager.MakeGroupCurrent(first),"active group");OperationsManager.UnSelectAllOperations();OperationsManager.InitOperationsManagerTree();ViewManager.RefreshPlanesManager();
    stage="save";Need(FileManager.Save(),"save revision");
   }else Need(mode=="read"&&string.Equals(Path.GetFullPath(FileManager.CurrentFileName),output,StringComparison.OrdinalIgnoreCase),"wrong revised document");
   stage="readback";var rows=new List<object>();ops=SearchManager.GetOperations();
   Need(MachineDefManager.GetCurrentMachineName().IndexOf("3 - AXIS VMC",StringComparison.OrdinalIgnoreCase)>=0,"wrong machine definition");
   r["machine_name"]=MachineDefManager.GetCurrentMachineName();
   var stock=MillStock.GetStockData();r["stock"]=O("origin",V(stock.StockOrigin),"size",V(stock.StockSize),"plane",PlaneRead(MachineDefManager.GetStockPlane()));
   foreach(var o in ops){var e=OperationsManager.GetOperationExtents(o.GetOperationID());Need(!o.Dirty&&e.IsDataValid&&e.IsTravelValid,"invalid path");
    Need(GroupManager.FindGroupByID(o.GroupNumber).Name==(o.Name.StartsWith("S1_")?"装夹1_正面_3道":"装夹2_翻面_6道"),"operation in wrong setup group");
    Need(o.WCS.ViewID==o.ToolPlane.ViewID&&o.WCS.ViewID==o.ConstructionPlane.ViewID,"tilted tool relative to setup WCS");
    bool s1=o.Name.StartsWith("S1_");Need(o.WCS.ViewName==(s1?"S1_TOP_G54":"S2_FLIP_G55")&&o.UseWCS&&o.UseToolPlane&&o.UseConstructionPlane,"setup plane binding");
    Need(o.WCS.ViewOrigin.x==0&&o.WCS.ViewOrigin.y==0&&o.WCS.ViewOrigin.z==(s1?10:0)&&o.WCS.ViewMatrix.Row3.z==(s1?1:-1),"setup orientation/origin changed");
    rows.Add(O("id",o.GetOperationID(),"name",o.Name,"group_id",o.GroupNumber,"group_name",GroupManager.FindGroupByID(o.GroupNumber).Name,"wcs",PlaneRead(o.WCS),"tool_plane",PlaneRead(o.ToolPlane),"construction_plane",PlaneRead(o.ConstructionPlane),"program",o.ProgramNumber,"top",o.Linking.TopStock,"depth",o.Linking.Depth,"clearance",o.Linking.Clearance,"retract",o.Linking.Retract,"feed_plane",o.Linking.FeedPlane,"dirty",o.Dirty,"world_min",V(e.WorldMin),"world_max",V(e.WorldMax),"cycle_seconds",o.CalcCycleTime(),"tool_number",o.OperationTool.Number,"tool_diameter",o.OperationTool.Diameter,"home_enabled",o.HomePosition.Enabled,"home",V((Point3D)o.HomePosition.Point),"feed",o.FeedRate,"rpm",o.SpindleSpeed,"plunge",o.PlungeRate,"retract_rate",o.RetractRate,"tool_assembly",O("length",o.OperationTool.Length,"flute_length",o.OperationTool.FluteLength,"shoulder_length",o.OperationTool.ShoulderLength,"shank_diameter",o.OperationTool.ShankDia,"holder_diameter",o.OperationTool.HolderDia,"holder_length",o.OperationTool.HolderLength,"tip_angle",o.OperationTool.TipAngle,"length_offset",o.LengthOffset,"diameter_offset",o.DiameterOffset)));
   }
   var sheets=new List<object>();for(int i=0;i<ViewSheets.GetSheetCount();i++){var d=new ViewSheets.ViewSheetData();Need(ViewSheets.GetViewSheetData(i,ref d),"read saved view sheet");sheets.Add(O("index",i,"name",ViewSheets.GetViewSheetName(i),"wcs_id",d.WcsPlaneID,"tool_plane_id",d.ToolPlaneID,"construction_plane_id",d.ConstructionPlaneID,"graphics_plane_id",d.GraphicsPlaneID,"has_bookmark",ViewSheets.SheetHasBookmark(i)));}
   r["operations"]=rows;r["view_sheets"]=sheets;
   Need(ViewSheets.GetSheetCount()==2,"two setup views required");
   if(mode=="read")Need(ViewSheets.GetViewSheetName(0)=="装夹1_正面_G54"&&ViewSheets.GetViewSheetName(1)=="装夹2_翻面_G55","setup view names lost: commit both labels with native UI Rename");
   r["view_label_ui_commit_required"]=mode=="apply";
   r["operations"]=rows;r["view_sheets"]=sheets;r["model"]=output;r["model_sha256"]=Hash(output);r["original_sha256"]=Hash(original);r["ok"]=true;
  }catch(Exception e){r["error"]=e.ToString();}
  r["stage"]=stage;File.WriteAllText(receipt,JsonSerializer.Serialize(r,new JsonSerializerOptions{WriteIndented=true}));
 }
}
