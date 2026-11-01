#r "System.Web.Extensions"
// Multi-operation specialization of the existing plan runner, software test only.
new AicncMulti().Run();
public sealed class AicncMulti {
    string requestPath=__REQUEST_PATH__,receiptPath=__RECEIPT_PATH__,mode=__MODE__,expected=__REQUEST_SHA256__,stage="preflight";
    System.Collections.Generic.Dictionary<string,object> request;
    System.Web.Script.Serialization.JavaScriptSerializer json=new System.Web.Script.Serialization.JavaScriptSerializer();
    System.Collections.Generic.List<System.Collections.Generic.Dictionary<string,object>> specs;
    public void Run(){
        var r=Obj("schema_version","aicnc.mastercam-plan-native-receipt/0.2","ok",false,"mode",mode,"pid",System.Diagnostics.Process.GetCurrentProcess().Id,"production_released",false,"regeneration_performed",false);
        try {
            Require(!System.IO.File.Exists(receiptPath),"Receipt exists");
            Require(Hash(requestPath)==expected,"Request drift");
            request=json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(System.IO.File.ReadAllText(requestPath));
            Require(S(request,"schema_version")=="aicnc.mastercam-plan-native-request/0.2" && S(request,"purpose")=="synthetic_native_validation","Request scope");
            foreach(string key in new[]{"plan","binding","target","step"})Require(Hash(S(request,key+"_path"))==S(request,key+"_sha256"),key+" drift");
            string model=System.IO.Path.GetFullPath(S(request,"model_path"));
            Require(System.IO.Path.GetDirectoryName(model)==System.IO.Path.GetDirectoryName(requestPath),"Output directory");
            Require(Mastercam.IO.SettingsManager.Metric,"Metric required");
            specs=new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string,object>>();
            foreach(object spec in (System.Collections.IEnumerable)request["operations"])specs.Add((System.Collections.Generic.Dictionary<string,object>)spec);
            Require(specs.Count>=2 && specs.Count<=64,"Operation count");
            r["request_sha256"]=expected;r["run_id"]=request["run_id"];
            r["api_version"]=typeof(Mastercam.IO.FileManager).Assembly.FullName;r["api_sha256"]=Hash(typeof(Mastercam.IO.FileManager).Assembly.Location);
            r["host_version"]=Mastercam.IO.FileManager.MastercamExeProductVersionName();
            if(mode=="create"){
                Require(!System.IO.File.Exists(model) && !System.IO.File.Exists(Mastercam.IO.FileManager.CurrentFileName),"Refuse existing file");
                Require(Mastercam.Support.SearchManager.GetGeometry().Length==0 && Mastercam.Support.SearchManager.GetOperations().Length==0,"Empty document required");
                var groups=new System.Collections.Generic.List<Mastercam.Support.Group>();Mastercam.Support.GroupManager.GetAllGroups(groups,true);Require(groups.Count==0,"Empty groups required");
                Step("machine");Require(Mastercam.Support.MachineDefManager.CreateMillMachineGroup(),"Create machine failed");
                var tools=new System.Collections.Generic.Dictionary<int,Mastercam.Database.Tool>();
                foreach(var spec in specs){
                    Step("create "+S(spec,"operation_id"));
                    var g=O(spec,"geometry");var t=O(spec,"tool");var cut=O(spec,"cutting_parameters");
                    int number=I(t,"number");Mastercam.Database.Tool tool;
                    if(!tools.TryGetValue(number,out tool)){
                        tool=S(t,"tool_type")=="drill"?(Mastercam.Database.Tool)new Mastercam.Tools.DrillTool():new Mastercam.Tools.EndMillFlatTool();
                        tool.IsMetric=true;tool.Number=number;tool.DiameterOffset=number;tool.LengthOffset=number;
                        tool.Diameter=D(t,"diameter");tool.Length=D(t,"length_mm");tool.FluteLength=D(t,"flute_length_mm");tool.ShoulderLength=D(t,"shoulder_length_mm");
                        tool.HolderDia=D(t,"holder_diameter_mm");tool.HolderLength=D(t,"holder_length_mm");tool.TipAngle=D(t,"tip_angle_deg");
                        tool.Flutes=(short)(tool.IsDrillTool?2:4);tool.Coolant=Mastercam.Database.Types.CoolantMode.COOL_OFF;
                        tool.RPM=I(cut,"spindle_speed_rpm");tool.Feed=D(cut,"feed_rate");tool.PlungeFeed=D(cut,"plunge_rate");tool.RetractFeed=500;
                        tool.FileName="AICNC synthetic "+S(t,"tool_id");Require(tool.Commit(),"Tool commit failed");tools.Add(number,tool);
                    }
                    Mastercam.Database.Operation op;
                    string kind=S(spec,"operation_type");
                    if(kind=="drilling"){
                        var drill=new Mastercam.Operations.DrillOperation();
                        drill.DrillCycle=Mastercam.Database.Types.DrillCycleType.Drill;drill.UseCustomParameters=false;drill.BreakThrough=0;drill.Dwell=0;
                        var points=new System.Collections.ArrayList();
                        foreach(object coords in (System.Collections.IEnumerable)g["points_mm"])points.Add(new Mastercam.Database.DrillPoint(P(coords)));
                        drill.DrillPoints=points;op=drill;
                    }else{
                        var origin=P(g["origin_mm"]);
                        var lines=Mastercam.GeometryUtility.GeometryCreationManager.CreateRectangle(origin,new Mastercam.Math.Point3D(origin.x+D(g,"width_mm"),origin.y+D(g,"height_mm"),origin.z));
                        var geometry=new Mastercam.Database.Geometry[lines.Length];for(int i=0;i<lines.Length;i++)geometry[i]=lines[i];
                        var chains=Mastercam.Database.ChainManager.ChainGeometry(geometry);Require(chains.Length==1 && chains[0].IsClosed,"Closed chain required");
                        chains[0].Direction=Mastercam.Database.Types.ChainDirectionType.CounterClockwise;
                        if(kind=="contouring"){
                            var contour=new Mastercam.Operations.ContourOperation();
                            contour.CutParams.ContourSubtype=Mastercam.Operations.Types.ContourSubtypeType.Basic;
                            contour.CutterComp.Type=Mastercam.Database.Types.CutterCompType.CutterCompComputer;
                            contour.CutterComp.Direction=Mastercam.Database.Types.CutterCompDir.CutterCompRight;
                            contour.CutterComp.RollCorners=Mastercam.Database.Types.CutterCompRoll.CutterCompRollNone;
                            contour.LeadInOut.Enabled=false;contour.SetChainArray(chains);op=contour;
                        }else if(kind=="pocketing"){
                            var pocket=new Mastercam.Operations.PocketOperation();
                            pocket.CutParams.PocketSubtype=Mastercam.Operations.Types.PocketSubtypeType.Standard;
                            pocket.CutParams.MachiningDirection=Mastercam.Database.Types.MachiningDirectionType.Climb;
                            pocket.CutParams.CreateAddtionalFinishOperation=false;pocket.CutParams.TipComp=false;
                            pocket.CutParams.LeaveStock.OnWalls=0;pocket.CutParams.LeaveStock.OnFloors=0;
                            pocket.Roughing.Enabled=true;pocket.Roughing.StepOverDistance=D(cut,"stepover");
                            pocket.Roughing.CuttingMethod=Mastercam.Database.Types.PocketCutTypes.ParallelSpiral;
                            pocket.PocketRoughEntry.EntryMode=Mastercam.Operations.Types.PocketRoughEntryMode.Off;
                            pocket.DepthCuts.Enabled=false;pocket.Finishing.Enabled=true;pocket.Finishing.FinishNumberPasses=1;
                            pocket.Finishing.SpringNumberPasses=0;pocket.Finishing.CutterComp=Mastercam.Database.Types.CutterCompType.CutterCompComputer;
                            pocket.Finishing.OverrideFeedrate=false;pocket.Finishing.OverrideSpindleSpeed=false;
                            pocket.SetChainArray(chains);op=pocket;
                        }else throw new System.Exception("Unsupported type");
                    }
                    op.Name=S(spec,"operation_name");op.OperationTool=tool;op.FeedRate=D(cut,"feed_rate");op.SpindleSpeed=I(cut,"spindle_speed_rpm");op.PlungeRate=D(cut,"plunge_rate");op.RetractRate=500;
                    op.LengthOffset=number;op.DiameterOffset=number;op.Coolant.OperationCoolant=Mastercam.Database.Types.CoolantMode.COOL_OFF;op.UseCoolantFromPost=false;
                    op.Linking.Clearance=10;op.Linking.ClearanceOn=true;op.Linking.ClearanceIncremental=false;op.Linking.ClearanceAssociative=false;
                    op.Linking.Retract=5;op.Linking.RetractOn=true;op.Linking.RetractIncremental=false;op.Linking.RetractAssociative=false;
                    op.Linking.FeedPlane=2;op.Linking.FeedPlaneIncremental=false;op.Linking.FeedPlaneAssociative=false;
                    op.Linking.TopStock=D(g,"top_mm");op.Linking.TopStockIncremental=false;op.Linking.TopStockAssociative=false;
                    op.Linking.Depth=D(g,"depth_mm");op.Linking.DepthIncremental=false;op.Linking.DepthAssociative=false;
                    Require(op.Commit(),"Operation commit failed");Step("regenerate "+S(spec,"operation_id"));Require(op.Regenerate(),"Regeneration failed");
                }
                r["regeneration_performed"]=true;Step("stock");
                var stockSpec=O(request,"stock");Require(Mastercam.Support.MillStock.SetToRectangularBoundingBox(P(stockSpec["min_mm"]),P(stockSpec["max_mm"])),"Stock failed");
                var stock=Mastercam.Support.MillStock.GetStockData();stock.DisplayStock=true;stock.SolidStock=false;Require(Mastercam.Support.MillStock.SetStockData(stock),"Stock commit failed");
                r["snapshot"]=Readback();Step("save");Mastercam.Operations.OperationsManager.RefreshOperationsManager();Mastercam.IO.GraphicsManager.FitScreen();
                Require(Mastercam.IO.FileManager.SaveAs(model,false),"Save failed");
            }else{
                Require(mode=="reopen" && System.String.Equals(System.IO.Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName),model,System.StringComparison.OrdinalIgnoreCase),"Reopen identity");
                Step("readback");r["snapshot"]=Readback();
            }
            r["model_path"]=model;r["current_file"]=Mastercam.IO.FileManager.CurrentFileName;r["model_sha256"]=Hash(model);r["model_size_bytes"]=new System.IO.FileInfo(model).Length;
            r["machine_sha256"]=Hash(Mastercam.Support.GroupManager.GetMachineNameInActiveGroup());r["ok"]=true;Step("complete");
        }catch(System.Exception e){r["error"]=e.ToString();}
        r["stage"]=stage;using(var stream=new System.IO.FileStream(receiptPath,System.IO.FileMode.CreateNew))using(var writer=new System.IO.StreamWriter(stream,new System.Text.UTF8Encoding(false)))writer.Write(json.Serialize(r));
    }
    object Readback(){
        var ops=Mastercam.Support.SearchManager.GetOperations();Require(ops.Length==specs.Count,"Operation coverage");var rows=new System.Collections.Generic.List<object>();
        for(int i=0;i<ops.Length;i++){
            var op=ops[i];Require(op.Name==S(specs[i],"operation_name")&&!op.Dirty,"Operation order/state");var t=op.OperationTool;Require(t!=null&&t.IsMetric,"Tool missing");
            var ext=Mastercam.Operations.OperationsManager.GetOperationExtents(op.GetOperationID());double zmax,zmin;bool zvalid=op.GetMaxAndMinZ(out zmax,out zmin);double seconds=op.CalcCycleTime();
            Require(ext!=null&&ext.IsDataValid&&ext.IsTravelValid&&zvalid&&seconds>0&&!double.IsNaN(seconds)&&!double.IsInfinity(seconds),"Empty path");
            var row=Obj("operation_id",op.GetOperationID(),"operation_name",op.Name,"operation_type",op.GetType().FullName,"dirty",op.Dirty,
                "feed_mm_min",op.FeedRate,"spindle_rpm",op.SpindleSpeed,"plunge_mm_min",op.PlungeRate,"retract_mm_min",op.RetractRate,"coolant",op.Coolant.OperationCoolant.ToString(),
                "depth_mm",op.Linking.Depth,"top_stock_mm",op.Linking.TopStock,"clearance_mm",op.Linking.Clearance,"retract_mm",op.Linking.Retract,"feed_plane_mm",op.Linking.FeedPlane,
                "length_offset",op.LengthOffset,"diameter_offset",op.DiameterOffset,
                "tool",Obj("type",t.GetType().FullName,"number",t.Number,"diameter_mm",t.Diameter,"length_mm",t.Length,"flute_length_mm",t.FluteLength,"shoulder_length_mm",t.ShoulderLength,"holder_diameter_mm",t.HolderDia,"holder_length_mm",t.HolderLength,"tip_angle_deg",t.TipAngle),
                "path",Obj("data_valid",ext.IsDataValid,"travel_valid",ext.IsTravelValid,"world_min",Point(ext.WorldMin),"world_max",Point(ext.WorldMax),"z_min_mm",zmin,"z_max_mm",zmax,"cycle_time_seconds",seconds,"wcs_id",ext.CommonWcsID,"tool_plane_id",ext.CommonTPlaneID));
            var chainOp=op as Mastercam.Operations.ChainBasedOperation;
            if(chainOp!=null){var chains=chainOp.GetChainArray();Require(chains.Length==1&&chains[0].IsClosed,"Chain lost");var curves=new System.Collections.Generic.List<object>();foreach(var c in Mastercam.Database.ChainManager.GetGeometryInChain(chains[0]))curves.Add(Obj("start",Point(c.EndPoint1),"end",Point(c.EndPoint2)));
                row["chain"]=Obj("closed",chains[0].IsClosed,"curves_count",chains[0].CurvesCount,"direction",chains[0].Direction.ToString(),"area_mm2",chains[0].Area,"perimeter_mm",chains[0].Perimeter,"curves",curves);}
            var drill=op as Mastercam.Operations.DrillOperation;if(drill!=null){var points=new System.Collections.Generic.List<object>();foreach(Mastercam.Database.DrillPoint point in drill.DrillPoints)points.Add(Point(point.PointData));row["drill_points"]=points;row["drill_cycle"]=drill.DrillCycle.ToString();}
            var pocket=op as Mastercam.Operations.PocketOperation;if(pocket!=null)row["pocket"]=Obj("stepover_mm",pocket.Roughing.StepOverDistance,"wall_stock_mm",pocket.CutParams.LeaveStock.OnWalls,"floor_stock_mm",pocket.CutParams.LeaveStock.OnFloors,"roughing",pocket.Roughing.Enabled,"finish",pocket.Finishing.Enabled,"entry",pocket.PocketRoughEntry.EntryMode.ToString());
            rows.Add(row);
        }
        return Obj("stock",Mastercam.Support.MillStock.GetStockData(),"metric",Mastercam.IO.SettingsManager.Metric,"geometry_count",Mastercam.Support.SearchManager.GetGeometry().Length,"operation_count",ops.Length,"operations",rows,"machine_name",Mastercam.Support.GroupManager.GetMachineNameInActiveGroup());
    }
    void Step(string s){stage=s;System.IO.File.WriteAllText(receiptPath+".progress",s);}
    static System.Collections.Generic.Dictionary<string,object> O(System.Collections.Generic.Dictionary<string,object> d,string k){return (System.Collections.Generic.Dictionary<string,object>)d[k];}
    static string S(System.Collections.Generic.Dictionary<string,object> d,string k){return (string)d[k];}
    static double D(System.Collections.Generic.Dictionary<string,object> d,string k){return System.Convert.ToDouble(d[k]);}
    static int I(System.Collections.Generic.Dictionary<string,object> d,string k){return System.Convert.ToInt32(d[k]);}
    static Mastercam.Math.Point3D P(object a){var v=new System.Collections.Generic.List<double>();foreach(object x in (System.Collections.IEnumerable)a)v.Add(System.Convert.ToDouble(x));Require(v.Count==3,"Point dimension");return new Mastercam.Math.Point3D(v[0],v[1],v[2]);}
    static object Point(Mastercam.Math.Point3D p){return new double[]{p.x,p.y,p.z};}
    static void Require(bool b,string m){if(!b)throw new System.Exception(m);}
    static string Hash(string p){using(var sha=System.Security.Cryptography.SHA256.Create())using(var stream=System.IO.File.OpenRead(p))return System.BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();}
    static System.Collections.Generic.Dictionary<string,object> Obj(params object[] p){var d=new System.Collections.Generic.Dictionary<string,object>();for(int i=0;i<p.Length;i+=2)d[(string)p[i]]=p[i+1];return d;}
}
