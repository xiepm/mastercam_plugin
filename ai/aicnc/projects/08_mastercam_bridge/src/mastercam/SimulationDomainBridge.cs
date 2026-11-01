// Version-bound adapter for Mastercam 2026's separate UBVS AppDomain.
// Build with .NET Framework. No vendor binaries are copied into the repository.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;

public sealed class SimulationDomainBridge : MarshalByRefObject
{
    static string targetPath, targetHash, configuredModel;
    float precisionGoal=0.015f, deviationThreshold=0.1f;
    int threadLimit=2;
    bool strictTolerances=false;
    float fixedPrecisionFactor;
    // Optional source-bound profile; existing 2026 callers retain their defaults.
    public void SetDiagnosticProfile(float precision, float deviation, int threads, float precisionFactor) {
        if(float.IsNaN(precision)||float.IsNaN(deviation)||float.IsNaN(precisionFactor)||precision<0.001f||precision>0.02f||deviation<precision||deviation>0.1f||threads<1||threads>2||precisionFactor<=0||precisionFactor>100)throw new ArgumentException("Invalid diagnostic profile");
        precisionGoal=precision;deviationThreshold=deviation;threadLimit=threads;fixedPrecisionFactor=precisionFactor;strictTolerances=true;
    }
    public override object InitializeLifetimeService() { return null; }
    public string Dispatch(string action, string receipt, string expectedTitle, string artifact)
    {
        if (File.Exists(receipt)) throw new IOException("Receipt exists; refuse replay");
        var app = Application.Current;
        if (app == null) throw new InvalidOperationException("Simulator Application missing");
        // Never synchronously wait on the simulator dispatcher from Mastercam's IPC thread.
        app.Dispatcher.BeginInvoke(DispatcherPriority.Background, new Action(() => {
            var result = Obj("schema_version", "aicnc.mastercam-simulator-receipt/0.1", "ok", false, "action", action, "pid", System.Diagnostics.Process.GetCurrentProcess().Id,
                "domain", AppDomain.CurrentDomain.FriendlyName, "utc", DateTime.UtcNow.ToString("O"), "production_released", false);
            try {
                object main = null;
                foreach (Window window in app.Windows) {
                    if (window.GetType().FullName != "UBVS.Views.MainWindow") continue;
                    if (!window.Title.EndsWith(expectedTitle, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("Simulator document mismatch: " + window.Title);
                    if (main != null) throw new InvalidOperationException("Multiple simulator windows");
                    main = Get(window.DataContext, "MainViewModel");
                }
                if (main == null) throw new InvalidOperationException("Simulator session missing");
                result["model_path"]=expectedTitle;
                result["simulator_version"]=main.GetType().Assembly.FullName;
                result["bridge_sha256"]=Hash(typeof(SimulationDomainBridge).Assembly.Location);
                var view = Get(main, "SimulationViewModel");
                var data = Get(view, "data");
                var simulation = Get(data, "simulation");
                if (!(bool)Get(data, "IsVerify")) throw new InvalidOperationException("Verify mode required");
                if(action=="diagnostic-settings") {
                    var allSettings=Get(data,"SimulationSettings");
                    var settingsTree=new Dictionary<string,object>();
                    foreach(var p in allSettings.GetType().GetProperties())if(p.GetIndexParameters().Length==0)try{var v=p.GetValue(allSettings,null);settingsTree[p.Name]=v==null?null:Scalars(v);}catch{}
                    foreach(var f in allSettings.GetType().GetFields())try{var v=f.GetValue(allSettings);settingsTree[f.Name]=v==null?null:Scalars(v);}catch{}
                    result["settings_tree"]=settingsTree;
                    foreach(var name in new[]{"CustomSettings","VerifySettings","Tolerances"}) {
                        var settings=Get(Get(data,"SimulationSettings"),name);
                        result[name]=Scalars(settings);
                        var members=new List<string>();
                        foreach(var p in settings.GetType().GetProperties())members.Add(p.Name+":"+p.PropertyType+" writable="+p.CanWrite);
                        foreach(var f in settings.GetType().GetFields())members.Add(f.Name+":"+f.FieldType+"="+f.GetValue(settings));
                        result[name+"_members"]=members;
                    }
                    var methods=new List<string>();foreach(var m in Get(data,"paramAdapter").GetType().GetMethods())if(m.Name.ToLowerInvariant().Contains("toler"))methods.Add(m.ToString());result["adapter_methods"]=methods;
                } else if(action=="motion-diagnostic") {
                    var stream=Get(Get(data,"DataProvider"),"VerifyOperations");var rows=new List<object>();
                    foreach(var op in (IEnumerable)stream){
                        var row=Obj("native_type",op.GetType().FullName,"scalars",Scalars(op),"tool_change",ValueTree(Get(op,"ToolChange"),5),"operation_info",Scalars(Get(op,"OperationInfo")));
                        var members=new List<string>();foreach(var p in op.GetType().GetProperties())members.Add(p.ToString());foreach(var m in op.GetType().GetMethods())if(m.Name.Contains("Move")||m.Name.Contains("Item"))members.Add(m.ToString());row["members"]=members;
                        var moves=new List<object>();if(op is IEnumerable)foreach(var move in (IEnumerable)op){if(moves.Count>=10000)throw new Exception("Motion audit limit");var mr=Obj("native_type",move.GetType().FullName,"scalars",Scalars(move),"move_data",ValueTree(Get(move,"MoveData"),5),"move_info",ValueTree(Get(move,"MoveInfo"),3),"wcs_matrix",Call(Get(move,"WCSMatrix"),"GetData"));moves.Add(mr);}row["moves"]=moves;rows.Add(row);
                    }result["streams"]=rows;
                } else if(action=="ready" || action=="ready-fine") {
                    var operations=Get(Get(data,"DataProvider"),"VerifyOperations");
                    result["ready"]=((ICommand)Get(view,"EndCommand")).CanExecute(null) && (bool)Get(operations,"IsComplete") && (int)Get(operations,"NumMoves")>0 && !(bool)Get(view,"IsSimulationBusy");
                    result["operation_count"]=Get(operations,"Count");result["num_moves"]=Get(operations,"NumMoves");
                    float precision=0;
                    foreach(var wrapper in (IEnumerable)Get(Get(simulation,"Verifier"),"AllInstances"))precision=Math.Max(precision,(float)Get(Get(wrapper,"InternalVerifier"),"Precision"));
                    result["precision_mm"]=precision;
                    if(action=="ready-fine")result["ready"]=(bool)result["ready"] && precision>0 && precision<=0.02f;

                } else if (action == "quality") {
                    // Same public settings/event path used by ParameterViewModel's
                    // precision control after its reset confirmation. The caller
                    // explicitly requested resetting this isolated software trial.
                    var verifySettings=Get(Get(data,"SimulationSettings"),"VerifySettings");
                    if(strictTolerances){Set(verifySettings,"AllowAutoAdjustPrecision",false);Set(Get(Get(data,"SimulationSettings"),"CustomSettings"),"AdaptiveQualityDisabled",true);}
                    var factor=verifySettings.GetType().GetField("PrecisionFactor");
                    var valueType=factor.FieldType.IsGenericType?factor.FieldType.GetGenericArguments()[0]:factor.FieldType;
                    var currentValue=factor.GetValue(verifySettings);
                    if(valueType!=factor.FieldType)currentValue=factor.FieldType.GetMethod("op_Implicit",new[]{factor.FieldType}).Invoke(null,new[]{currentValue});
                    double oldFactor=Convert.ToDouble(currentValue);
                    float oldPrecision=0;
                    foreach(var wrapper in (IEnumerable)Get(Get(simulation,"Verifier"),"AllInstances")){
                        var native=Get(wrapper,"InternalVerifier");Set(native,"LimitThreadCount",threadLimit);
                        oldPrecision=Math.Max(oldPrecision,(float)Get(native,"Precision"));
                    }
                    if(oldPrecision<=0 || oldFactor<=0)throw new InvalidOperationException("Invalid initial precision");
                    double newFactor=strictTolerances?fixedPrecisionFactor:oldFactor*oldPrecision/precisionGoal;
                    object factorValue=Convert.ChangeType(newFactor,valueType,System.Globalization.CultureInfo.InvariantCulture);
                    if(valueType!=factor.FieldType)factorValue=factor.FieldType.GetMethod("op_Implicit",new[]{valueType}).Invoke(null,new[]{factorValue});
                    factor.SetValue(verifySettings,factorValue);
                    var flags=Enum.ToObject(NativeType("ModuleWorks.SettingsCategoryFlags"),8);
                    Call(Get(Get(main,"ParameterViewModel"),"SimulationSettingsProvider"),"FireSimulationResetRequired",flags);
                    result["requested_precision_mm"]=precisionGoal;result["precision_factor"]=newFactor;result["reset_requested"]=true;
                } else if (action == "configure") {
                    if(!File.Exists(artifact))throw new FileNotFoundException("Target missing",artifact);
                    targetPath=Path.GetFullPath(artifact);targetHash=Hash(artifact);configuredModel=expectedTitle;
                    var options=Get(main,"CollisionDetectionOptions");
                    foreach(var name in new[]{"CheckStockAgainstMillingHolder","CheckStockAgainstMillingShank","CheckStockAgainstMillingShoulder"})
                        Set(options,name,true);
                    var custom=Get(Get(data,"SimulationSettings"),"CustomSettings");
                    Set(custom,"CollCheck",true); Set(custom,"MwSimCollCheckBetweenMoves",true);
                    if(strictTolerances) {
                        // Tool changes reapply these upstream settings to the verifier.
                        var tolerances=Get(Get(data,"SimulationSettings"),"Tolerances");
                        Set(tolerances,"CuttingTolerance",precisionGoal);
                        Set(tolerances,"CollisionTolerance",deviationThreshold);
                        Set(tolerances,"HolderCollisionTolerance",deviationThreshold);
                        foreach(var name in new[]{"CollisionCheckerToolProfileTolerance","CollisionCheckerHolderToolProfileTolerance","ToolMeshProfileTolerance","ArcInterpolationTolerance"})Set(tolerances,name,precisionGoal);
                    }
                    var provider=Get(data,"DataProvider");
                    var world=Call(Get(provider,"DefaultStockPosition"),"GetData") as double[];
                    result["stock_to_world"]=world;
                    var inverse=Call(Get(provider,"DefaultStockPosition"),"Inverted");
                    var matrix=Matrix((double[])Call(inverse,"GetData"));
                    var mesh=ReadMesh(artifact); Call(mesh,"Transform",matrix);
                    foreach(var wrapper in (IEnumerable)Get(Get(simulation,"Verifier"),"AllInstances")) {
                        var native=Get(wrapper,"InternalVerifier");
                        result["original_cutting_tolerance_mm"]=Get(native,"CuttingTolerance");
                        result["original_thread_limit"]=Get(native,"LimitThreadCount");
                        Set(native,"LimitThreadCount",threadLimit);
                        if(strictTolerances){Set(native,"CuttingTolerance",precisionGoal);Set(native,"CollisionTolerance",deviationThreshold);Set(native,"HolderCollisionTolerance",deviationThreshold);}
                        Call(native,"SetTarget",mesh);
                        Set(native,"GougeThreshold",-deviationThreshold); Set(native,"ExcessThreshold",deviationThreshold);
                        result["target_count"]=Get(native,"TargetCount");
                    }
                    result["collision_options"]=Scalars(options);
                    var behavior=Call(Get(data,"paramAdapter"),"GetToolbehaviour",false,false,false);
                    result["configured_holder"]=Scalars(Get(behavior,"Holder"));
                    result["configured_shaft"]=Scalars(Get(behavior,"Shaft"));
                    result["configured_arbor"]=Scalars(Get(behavior,"Arbor"));
                } else if (action == "run") {
                    if(configuredModel!=expectedTitle || targetHash!=Hash(targetPath))throw new InvalidOperationException("Configure target before run");
                    if ((bool)Get(view, "IsSimulationBusy")) throw new InvalidOperationException("Simulation busy");
                    var end=(ICommand)Get(view,"EndCommand");
                    result["can_execute_end"]=end.CanExecute(null);
                    if(!end.CanExecute(null))throw new InvalidOperationException("Simulator End command is not ready");
                    end.Execute(null);
                    result["request_accepted"] = true;
                } else if (action == "close") {
                    ((ICommand)Get(main, "CloseCommand")).Execute(null);
                } else if (action == "inspect" || action == "export") {
                    var ops = Get(Get(data, "DataProvider"), "VerifyOperations");
                    var position = Get(Get(data, "player"), "SimulatedPosition");
                    int count = (int)Get(ops, "NumMoves");
                    bool complete = position!=null && (bool)Get(ops, "IsComplete") && count > 0 &&
                        (int)Get(position, "Index") == count - 1 &&
                        !(bool)Get(view, "IsSimulationBusy") && !(bool)Get(view, "IsRunning");
                    result["motion"] = Obj("operation_count", Get(ops,"Count"), "num_moves", count,
                        "input_complete", Get(ops,"IsComplete"), "position", position==null?null:Scalars(position),
                        "is_running", Get(view,"IsRunning"), "is_busy", Get(view,"IsSimulationBusy"),
                        "completed", complete);
                    result["operation_stream"]=OperationRows(ops);
                    result["target_path"]=targetPath; result["target_sha256"]=targetHash;
                    if(configuredModel!=expectedTitle || targetHash!=Hash(targetPath))throw new InvalidOperationException("Target binding changed");
                    result["collision_options"] = Scalars(Get(main,"CollisionDetectionOptions"));
                    var settings = Get(data,"SimulationSettings");
                    var custom=Get(settings,"CustomSettings");
                    result["checks"] = Obj("enabled",Get(custom,"CollCheck"),"between_moves",Get(custom,"MwSimCollCheckBetweenMoves"));
                    if(strictTolerances)result["quality_policy"]=Obj("adaptive_quality_disabled",Get(custom,"AdaptiveQualityDisabled"),"allow_auto_adjust_precision",Get(Get(settings,"VerifySettings"),"AllowAutoAdjustPrecision"),"cutting_tolerance_mm",Call(Get(data,"paramAdapter"),"GetCuttingTolerance"),"collision_tolerance_mm",Call(Get(data,"paramAdapter"),"GetCollisionTolerance"),"holder_tolerance_mm",Call(Get(data,"paramAdapter"),"GetHolderCollisionTolerance"));
                    result["stock_to_world"]=Call(Get(Get(data,"DataProvider"),"DefaultStockPosition"),"GetData");
                    var verifiers = new List<object>();
                    foreach (var wrapper in (IEnumerable)Get(Get(simulation,"Verifier"),"AllInstances")) {
                        var native = Get(wrapper,"InternalVerifier");
                        var behavior = Get(native,"ToolBehavior");
                        var item = Obj("precision_mm", Get(native,"Precision"),
                            "cutting_tolerance_mm",Get(native,"CuttingTolerance"),
                            "thin_volume_tolerance_mm",Get(native,"ThinVolumeTolerance"),
                            "thread_limit",Get(native,"LimitThreadCount"),
                            "max_memory_load",Get(native,"MaxMemoryLoad"),
                            "initial_volume_mm3", Get(native,"InitialStockVolume"),
                            "current_volume_mm3", Get(native,"CurrentStockVolume"),
                            "target_count", Get(native,"TargetCount"),
                            "collision_tolerance_mm",Get(native,"CollisionTolerance"),
                            "holder_tolerance_mm",Get(native,"HolderCollisionTolerance"),
                            "holder",Scalars(Get(behavior,"Holder")), "shaft",Scalars(Get(behavior,"Shaft")),
                            "arbor",Scalars(Get(behavior,"Arbor")), "flute",Scalars(Get(behavior,"Flute")));
                        if (action == "export") {
                            if (!complete) throw new InvalidOperationException("Motion not complete");
                            if (File.Exists(artifact) || File.Exists(artifact+".local.stl")) throw new IOException("IPW exists");
                            Call(native,"SaveMesh",artifact+".local.stl",0.001f);
                            var mesh=ReadMesh(artifact+".local.stl");
                            Call(mesh,"Transform",Matrix((double[])result["stock_to_world"]));
                            Stl("WriteSTL",artifact,mesh);
                            item["ipw_path"] = artifact;
                            if ((int)Get(native,"TargetCount") > 0) {
                                Call(native,"CalculateGougeExcess");
                                item["gouge_threshold_mm"]=Get(native,"GougeThreshold");
                                item["excess_threshold_mm"]=Get(native,"ExcessThreshold");
                                item["gouge_report_mode"]=Call(native,"GetGougeReportMode").ToString();
                                item["gouges"] = Sequence(Call(native,"GetGougeList"));
                                item["excess"] = Sequence(Call(native,"GetExcessList"));
                            }
                        }
                        verifiers.Add(item);
                    }
                    result["verifiers"] = verifiers;
                    result["report_groups"] = Sequence(Get(Get(Get(view,"ReportViewModel"),"Value"),"ReportItemGroups"));
                } else throw new ArgumentException("Unsupported action");
                result["ok"] = true;
            } catch (Exception error) { result["error"] = error.ToString(); }
            // Publish only after the asynchronous writer has closed the file.
            // Seeing an empty CreateNew file is not a completed native receipt.
            using (var stream = new FileStream(receipt+".partial",FileMode.CreateNew))
            using (var writer = new StreamWriter(stream)) writer.Write(new JavaScriptSerializer().Serialize(result));
            File.Move(receipt+".partial",receipt);
        }));
        return "scheduled";
    }
    static Type NativeType(string name) {
        foreach(var assembly in AppDomain.CurrentDomain.GetAssemblies()) {
            var type=assembly.GetType(name); if(type!=null)return type;
        }
        throw new TypeLoadException(name);
    }
    static object Matrix(double[] values) {
        var result=new float[values.Length];for(int i=0;i<values.Length;i++)result[i]=(float)values[i];
        return Activator.CreateInstance(NativeType("ModuleWorks.TransformationMatrixManaged"),new object[]{result});
    }
    static object ReadMesh(string path) {
        var unit=Enum.Parse(NativeType("ModuleWorks.Unit"),"Metric");
        var mesh=Activator.CreateInstance(NativeType("ModuleWorks.Meshf"),new object[]{unit});
        Stl("ReadSTL",path,mesh);return mesh;
    }
    static void Stl(string name,string path,object mesh) {
        var type=NativeType("ModuleWorks.STLTranslatorf");
        var method=type.GetMethod(name,BindingFlags.Public|BindingFlags.Static|BindingFlags.Instance|BindingFlags.FlattenHierarchy,null,new[]{typeof(string),mesh.GetType()},null);
        method.Invoke(method.IsStatic?null:Activator.CreateInstance(type),new[]{(object)path,mesh});
    }
    static void Set(object obj,string name,object value) {
        var property=obj.GetType().GetProperty(name);
        if(property!=null){property.SetValue(obj,value,null);return;}
        var field=obj.GetType().GetField(name);
        if(field==null)throw new MissingMemberException(obj.GetType().FullName,name);
        if(value!=null && !field.FieldType.IsInstanceOfType(value)) {
            var conversion=field.FieldType.GetMethod("op_Implicit",new[]{value.GetType()});
            if(conversion!=null)value=conversion.Invoke(null,new[]{value});
        }
        field.SetValue(obj,value);
    }
    static object Get(object obj, string name) {
        if(obj==null)throw new InvalidOperationException("Null owner while reading "+name);
        for (var type = obj.GetType(); type != null; type = type.BaseType) {
            var property = type.GetProperty(name,BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly);
            if (property != null) return property.GetValue(obj,null);
            var field = type.GetField(name,BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly);
            if (field != null) return field.GetValue(obj);
        }
        throw new MissingMemberException(obj.GetType().FullName,name);
    }
    static object Call(object obj, string name, params object[] args) {
        foreach (var method in obj.GetType().GetMethods(BindingFlags.Public|BindingFlags.Instance)) {
            if(method.Name != name || method.GetParameters().Length != args.Length) continue;
            bool matches=true; var ps=method.GetParameters();
            for(int i=0;i<args.Length;i++) if(args[i]!=null && !ps[i].ParameterType.IsInstanceOfType(args[i])) matches=false;
            if(matches)return method.Invoke(obj,args);
        }
        throw new MissingMethodException(obj.GetType().FullName,name);
    }
    static string Hash(string path) { using(var sha=System.Security.Cryptography.SHA256.Create()) using(var stream=File.OpenRead(path)) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
    static object Sequence(object obj) { return SequenceAt(obj,0); }
    static object OperationRows(object stream) {
        var rows=new List<object>();foreach(var op in (IEnumerable)stream){
            var row=Scalars(op);row["operation_info"]=Scalars(Get(op,"OperationInfo"));
            var tool=Get(op,"Tool");row["has_tool"]=Get(tool,"HasValue");
            if((bool)row["has_tool"])row["tool_metadata"]=Scalars(Get(tool,"Value"));
            rows.Add(row);
        }return rows;
    }
    static object ValueTree(object obj,int depth) {
        if(obj==null)return null;var t=obj.GetType();if(t.IsEnum)return obj.ToString();if(t.IsPrimitive||obj is string||obj is decimal)return obj;
        if(depth<0)return Obj("unexpanded_type",t.FullName);
        if(t.IsGenericType&&t.Name.StartsWith("Optional")){bool has=(bool)Get(obj,"HasValue");return Obj("has_value",has,"value",has?ValueTree(Get(obj,"Value"),depth-1):null);}
        if(obj is IEnumerable){var list=new List<object>();foreach(var v in (IEnumerable)obj){if(list.Count>=1000)throw new Exception("Value audit limit");list.Add(ValueTree(v,depth-1));}return list;}
        var r=Obj("native_type",t.FullName);foreach(var p in t.GetProperties(BindingFlags.Public|BindingFlags.Instance))if(p.CanRead&&p.GetIndexParameters().Length==0)try{r[p.Name]=ValueTree(p.GetValue(obj,null),depth-1);}catch(Exception e){r[p.Name]=Obj("read_error",e.GetBaseException().Message);}
        foreach(var f in t.GetFields(BindingFlags.Public|BindingFlags.Instance))r[f.Name]=ValueTree(f.GetValue(obj),depth-1);return r;
    }
    static object SequenceAt(object obj,int depth) {
        var list=new List<object>(); foreach(var item in (IEnumerable)obj) {
            if(list.Count>=1000)throw new InvalidOperationException("Report exceeds audit limit");
            var row=Scalars(item);row["native_type"]=item.GetType().FullName;
            if(depth<3)foreach(var property in item.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
                if(property.GetIndexParameters().Length!=0||!property.CanRead||property.PropertyType==typeof(string))continue;
                if(typeof(IEnumerable).IsAssignableFrom(property.PropertyType)) {
                    var value=property.GetValue(item,null);if(value!=null)row[property.Name]=SequenceAt(value,depth+1);
                }
            }
            list.Add(row);
        } return list;
    }
    static Dictionary<string,object> Scalars(object obj) {
        var result=new Dictionary<string,object>();
        foreach(var p in obj.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
            if(p.GetIndexParameters().Length!=0 || !p.CanRead)continue;
            if(p.PropertyType.IsPrimitive || p.PropertyType.IsEnum || p.PropertyType==typeof(string)) {
                var value=p.GetValue(obj,null);result[p.Name]=p.PropertyType.IsEnum?value.ToString():value;
            }
        }
        foreach(var f in obj.GetType().GetFields(BindingFlags.Public|BindingFlags.Instance))
            if(f.FieldType.IsPrimitive||f.FieldType.IsEnum||f.FieldType==typeof(string)) {
                var value=f.GetValue(obj);result[f.Name]=f.FieldType.IsEnum?value.ToString():value;
            }
        return result;
    }
    static Dictionary<string,object> Obj(params object[] pairs) {var d=new Dictionary<string,object>();for(int i=0;i<pairs.Length;i+=2)d[(string)pairs[i]]=pairs[i+1];return d;}
}
