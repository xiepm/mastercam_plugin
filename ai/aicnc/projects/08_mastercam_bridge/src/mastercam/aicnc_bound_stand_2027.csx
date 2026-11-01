#r "__SYSTEM_TEXT_JSON__"
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Collections.Generic;
using Mastercam.Math;
using Mastercam.Database;
using Mastercam.Operations;
using Mastercam.Database.Types;
using Mastercam.Operations.Types;
// Explicit source-bound extension of the P08 multi-operation native pattern.
new StandTrial().Run(__ROOT__, __MODE__, __RECEIPT__);
public sealed class StandTrial {
 string root, stage="preflight";
 static Point3D P(double x,double y,double z){return new Point3D(x,y,z);}
 static string Hash(string p){return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();}
 static void Need(bool b,string why){if(!b)throw new Exception(why);}
 static double D(JsonElement e,string k){return e.GetProperty(k).GetDouble();}
 static string S(JsonElement e,string k){return e.GetProperty(k).GetString();}
 static Dictionary<string,object> O(params object[] a){var d=new Dictionary<string,object>();for(int i=0;i<a.Length;i+=2)d[(string)a[i]]=a[i+1];return d;}
 MCView Plane(string name,bool bottom){var v=Mastercam.IO.ViewManager.GetAllViews(true).SingleOrDefault(x=>x.ViewName==name);if(v==null){v=new MCView();Need(v.Commit(),"plane initialize");}if(v.ViewName!=name)v.ViewName=name;v.ViewOrigin=P(0,0,0);v.ViewMatrix=new Matrix3D(P(1,0,0),P(0,bottom?-1:1,0),P(0,0,bottom?-1:1));Need(v.Commit(),"plane commit");v.Retrieve();Need(v.ViewName==name&&Math.Abs(v.ViewMatrix.Row3.z-(bottom?-1:1))<1e-10,"plane readback");return v;}
 Chain[] Outline(MCView view,double z,bool circle){
  Mastercam.IO.SelectionManager.UnselectAllGeometry();
  var geos=new List<Geometry>();
  Func<double,double,double,Point3D> world=(x,y,a)=>view.ViewMatrix.Row3.z<0?P(x,-y,-a):P(x,y,a);
  if(circle)geos.Add(new Mastercam.Curves.ArcGeometry(view,P(0,0,z),5.125,0,360));
  else {
   var cs=new[]{new[]{5.0,5.0,0.0},new[]{-5.0,5.0,90.0},new[]{-5.0,-5.0,180.0},new[]{5.0,-5.0,270.0}};
   foreach(var c in cs)geos.Add(new Mastercam.Curves.ArcGeometry(view,P(c[0],c[1],z),2.8,c[2],c[2]+90));
   geos.Add(new Mastercam.Curves.LineGeometry(world(5,7.8,z),world(-5,7.8,z)));
   geos.Add(new Mastercam.Curves.LineGeometry(world(-7.8,5,z),world(-7.8,-5,z)));
   geos.Add(new Mastercam.Curves.LineGeometry(world(-5,-7.8,z),world(5,-7.8,z)));
   geos.Add(new Mastercam.Curves.LineGeometry(world(7.8,-5,z),world(7.8,5,z)));
  }
  foreach(var g in geos){g.Level=100;Need(g.Commit(),"curve commit");Need(g.Retrieve(),"curve database readback");}
  var chains=ChainManager.ChainGeometry(geos.ToArray());Need(chains.Length==1&&chains[0].IsClosed,"chain not closed");chains[0].Direction=ChainDirectionType.CounterClockwise;return chains;
 }
 public void Run(string folder,string mode,string receipt){
  root=folder;var r=O("ok",false,"mode",mode,"pid",Environment.ProcessId,"production_released",false);
  try{
   Need(!File.Exists(receipt),"receipt exists");
   var req=JsonDocument.Parse(File.ReadAllText(root+"/trial-binding.json")).RootElement;
   Need(S(req,"scope")=="user_part_software_simulation","scope");
   Need(S(req,"source_sha256")=="68fb222f6d144c1673c98f9722b76d05c2eb4d9bdf2b22a7e47bf986e36c1429","unsupported source profile");
   Need(Hash(root+"/source.step")==S(req,"source_sha256")&&Hash(root+"/cam_plan.json")==S(req,"plan_sha256")&&Hash(root+"/target.stl")==S(req,"target_sha256"),"source drift");
   var specs=req.GetProperty("operations").EnumerateArray().ToArray();Need(specs.Length==9,"coverage");
   string model=Path.GetFullPath(root+"/stand-2setup.mcam");
   if(mode=="create"||mode=="resume"){
    Need(!File.Exists(model),"output exists");var existing=Mastercam.Support.SearchManager.GetOperations();Need(mode=="create"?existing.Length==0&&Mastercam.Support.SearchManager.GetGeometry().Length==1:(existing.Length==3||existing.Length==8),"unexpected source state");
    Need(Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName).Equals(Path.GetFullPath(root+"/source.mcam"),StringComparison.OrdinalIgnoreCase),"wrong active source");
    Need(Mastercam.IO.SettingsManager.Metric,"mm required");
    if(mode=="create")Need(Mastercam.Support.MachineDefManager.CreateMillMachineGroup(),"machine group");
    var top=Plane("STAND_TOP_PCS",false);var bottom=Plane("STAND_BOTTOM_PCS",true);
    var tools=new Dictionary<int,Tool>();
    for(int i=0;i<existing.Length;i++){var o=existing[i];Need(o.Name==S(specs[i],"name")&&!o.Dirty,"resume identity/path");tools[o.OperationTool.Number]=o.OperationTool;}
    foreach(var spec in specs){
     string role=S(spec,"role");stage=role;File.WriteAllText(receipt+".progress",stage);
     if(existing.Any(o=>o.Name==S(spec,"name")))continue;
     bool underside=spec.GetProperty("bottom").GetBoolean();var plane=underside?bottom:top;
     Mastercam.IO.ViewManager.WorkCoordinateSystem=top;Mastercam.IO.ViewManager.CPlane=plane;Mastercam.IO.ViewManager.TPlane=plane;
     var ts=spec.GetProperty("tool");int no=spec.GetProperty("tool_number").GetInt32();Tool tool;
     if(!tools.TryGetValue(no,out tool)){
      string typ=S(ts,"tool_type");tool=typ=="drill"?(Tool)new Mastercam.Tools.DrillTool():typ=="chamfer_mill"?(Tool)new Mastercam.Tools.ChamferMillTool():new Mastercam.Tools.EndMillFlatTool();
      tool.IsMetric=true;tool.Number=no;tool.LengthOffset=no;tool.DiameterOffset=no;tool.Diameter=D(ts,"diameter");tool.Length=40;tool.FluteLength=typ=="chamfer_mill"?2.75:15;tool.ShoulderLength=20;tool.ShankDia=tool.Diameter;tool.ShoulderDia=tool.Diameter;tool.HolderDia=20;tool.HolderLength=40;tool.TipAngle=typ=="drill"?118:typ=="chamfer_mill"?45:0;tool.Flutes=(short)(typ=="drill"?2:4);tool.Coolant=CoolantMode.COOL_OFF;tool.RPM=3000;tool.Feed=150;tool.PlungeFeed=60;tool.RetractFeed=500;tool.FileName="";tool.Name="SIMULATION_ONLY_"+S(ts,"tool_id");if(typ=="chamfer_mill"){var a=tool.MillToolAttributes;a.TipDia=.5;tool.MillToolAttributes=a;}Need(tool.Commit(),"tool commit");tools[no]=tool;
     }
     Operation op;
     if(role=="through"||role.StartsWith("blind_")){
      var o=new DrillOperation();o.DrillCycle=DrillCycleType.Drill;o.UseCustomParameters=false;o.BreakThrough=0;o.Dwell=0;
      var a=spec.GetProperty("origin").EnumerateArray().Select(x=>x.GetDouble()).ToArray();o.DrillPoints=new System.Collections.ArrayList{new DrillPoint(P(a[0],a[1],a[2]))};op=o;
     }else if(role=="counterbore"){
      var o=new PocketOperation();o.CutParams.PocketSubtype=PocketSubtypeType.Standard;o.CutParams.MachiningDirection=MachiningDirectionType.Climb;o.CutParams.CreateAddtionalFinishOperation=false;o.CutParams.TipComp=false;o.CutParams.LeaveStock.OnWalls=0;o.CutParams.LeaveStock.OnFloors=0;
      o.Roughing.Enabled=true;o.Roughing.StepOverDistance=1;o.Roughing.CuttingMethod=PocketCutTypes.ParallelSpiral;o.PocketRoughEntry.EntryMode=PocketRoughEntryMode.Off;o.DepthCuts.Enabled=true;o.DepthCuts.MaxRoughStep=1;o.DepthCuts.FinishNumberCuts=0;o.Finishing.Enabled=true;o.Finishing.FinishNumberPasses=1;o.Finishing.SpringNumberPasses=0;o.Finishing.CutterComp=CutterCompType.CutterCompComputer;o.SetChainArray(Outline(plane,0,true));op=o;
     }else{
      var o=new ContourOperation();bool chamfer=role.EndsWith("chamfer");o.CutParams.ContourSubtype=chamfer?ContourSubtypeType.Chamfer2D:ContourSubtypeType.Basic;o.CutterComp.Type=CutterCompType.CutterCompComputer;o.CutterComp.Direction=CutterCompDir.CutterCompRight;o.CutterComp.RollCorners=CutterCompRoll.CutterCompRollNone;o.LeadInOut.Enabled=false;
      o.DepthCuts.Enabled=!chamfer;o.DepthCuts.MaxRoughStep=1;o.DepthCuts.FinishNumberCuts=0;
      if(chamfer){o.Chamfer.Width=.2;o.Chamfer.ToolTipOffset=.5;o.Chamfer.Depth=.2;}
      o.SetChainArray(Outline(plane,D(spec,"top"),false));op=o;
     }
     op.Name=S(spec,"name");op.WCS=top;op.ConstructionPlane=plane;op.ToolPlane=plane;op.UseWCS=true;op.UseToolPlane=true;op.UseConstructionPlane=true;
     op.OperationTool=tool;op.FeedRate=150;op.SpindleSpeed=3000;op.PlungeRate=60;op.RetractRate=500;op.LengthOffset=no;op.DiameterOffset=no;op.Coolant.OperationCoolant=CoolantMode.COOL_OFF;op.UseCoolantFromPost=false;
     double z=D(spec,"top");op.Linking.Clearance=z+10;op.Linking.ClearanceOn=true;op.Linking.ClearanceIncremental=false;op.Linking.ClearanceAssociative=false;op.Linking.Retract=z+5;op.Linking.RetractOn=true;op.Linking.RetractIncremental=false;op.Linking.RetractAssociative=false;op.Linking.FeedPlane=z+2;op.Linking.FeedPlaneIncremental=false;op.Linking.FeedPlaneAssociative=false;op.Linking.TopStock=z;op.Linking.TopStockIncremental=false;op.Linking.TopStockAssociative=false;op.Linking.Depth=D(spec,"depth");op.Linking.DepthIncremental=false;op.Linking.DepthAssociative=false;
     Need(op.Commit(),"operation commit "+role);Need(op.Regenerate(),"regenerate "+role);
    }
    Mastercam.IO.ViewManager.WorkCoordinateSystem=top;Mastercam.IO.ViewManager.CPlane=top;Mastercam.IO.ViewManager.TPlane=top;
    Need(Mastercam.Support.MillStock.SetToRectangularBoundingBox(P(-9,-9,0),P(9,9,10)),"stock");var stock=Mastercam.Support.MillStock.GetStockData();stock.DisplayStock=true;stock.SolidStock=false;Need(Mastercam.Support.MillStock.SetStockData(stock),"stock commit");
    Mastercam.Operations.OperationsManager.RefreshOperationsManager();Mastercam.IO.GraphicsManager.FitScreen();Need(Mastercam.IO.FileManager.SaveAs(model,false),"save");Mastercam.IO.FileManager.CurrentFileName=model;Need(Mastercam.IO.FileManager.Save(),"save active filename");
   }else Need(mode=="reopen"&&Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName).Equals(Path.GetFullPath(model),StringComparison.OrdinalIgnoreCase),"reopen identity");
   var ops=Mastercam.Support.SearchManager.GetOperations();Need(ops.Length==9,"native coverage");var rows=new List<object>();
   for(int i=0;i<ops.Length;i++){
    var o=ops[i];var t=o.OperationTool;var e=OperationsManager.GetOperationExtents(o.GetOperationID());double seconds=o.CalcCycleTime();Need(!o.Dirty&&e.IsDataValid&&e.IsTravelValid&&seconds>0,"invalid path "+o.Name);
    var spec=specs[i];Need(o.Name==S(spec,"name")&&t.Number==spec.GetProperty("tool_number").GetInt32()&&Math.Abs(t.Diameter-D(spec.GetProperty("tool"),"diameter"))<1e-9,"operation/tool binding "+o.Name);
    Need(Math.Abs(o.Linking.Depth-D(spec,"depth"))<1e-9&&Math.Abs(o.Linking.TopStock-D(spec,"top"))<1e-9,"depth drift "+o.Name);
    Need(Math.Abs(o.ToolPlane.ViewMatrix.Row3.z-(spec.GetProperty("bottom").GetBoolean()?-1:1))<1e-9&&Math.Abs(o.WCS.ViewMatrix.Row3.z-1)<1e-9,"plane drift "+o.Name);
    Need(string.IsNullOrEmpty(t.FileName)&&t.Length==40&&t.HolderDia==20&&t.HolderLength==40,"tool assembly/reference drift "+o.Name);
    rows.Add(O("name",o.Name,"id",o.GetOperationID(),"type",o.GetType().Name,"dirty",o.Dirty,"depth",o.Linking.Depth,"top",o.Linking.TopStock,"tool",t.Number,"diameter",t.Diameter,"tip_angle",t.TipAngle,"length",t.Length,"flutes",t.FluteLength,"holder_diameter",t.HolderDia,"feed",o.FeedRate,"rpm",o.SpindleSpeed,"plane",o.ToolPlane.ViewName,"wcs",o.WCS.ViewName,"world_min",new[]{e.WorldMin.x,e.WorldMin.y,e.WorldMin.z},"world_max",new[]{e.WorldMax.x,e.WorldMax.y,e.WorldMax.z},"cycle_seconds",seconds));
   }
   var savedStock=Mastercam.Support.MillStock.GetStockData();Need(savedStock.StockSize.x==18&&savedStock.StockSize.y==18&&savedStock.StockSize.z==10&&!savedStock.SolidStock,"stock drift");r["stock_size_mm"]=new[]{savedStock.StockSize.x,savedStock.StockSize.y,savedStock.StockSize.z};
   r["operations"]=rows;r["model_path"]=model;r["model_sha256"]=Hash(model);r["plan_sha256"]=S(req,"plan_sha256");r["source_sha256"]=S(req,"source_sha256");r["ok"]=true;
  }catch(Exception e){r["error"]=e.ToString();}
  r["stage"]=stage;File.WriteAllText(receipt,JsonSerializer.Serialize(r,new JsonSerializerOptions{WriteIndented=true}));
 }
}




