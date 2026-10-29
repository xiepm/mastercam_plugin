using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Operations;
using Mastercam.Tools;
using PorscheAdvanced2027;
using Ad=AdvancedDrill2027;
using Tap=AdvancedDrillTap2027;
using Boundary=MastercamPluginAI.BoundaryAdapter;
using Middle=MiddleConfirm2027;
namespace MastercamPluginAI;
public static class PanelBindings
{
    static readonly JsonSerializerOptions Json=new(){IncludeFields=true,Converters={new JsonStringEnumConverter()},UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    static string Encode(object value)=>JsonSerializer.Serialize(value,Json);
    static T Read<T>(JsonElement e)=>JsonSerializer.Deserialize<T>(e.GetRawText(),Json);
    static int I(JsonElement e,string key)=>e.GetProperty(key).GetInt32();
    static double N(JsonElement e,string key)=>e.GetProperty(key).GetDouble();
    static string S(JsonElement e,string key)=>e.GetProperty(key).GetString();
    static Tap.Vec V(JsonElement e)=>new(N(e,"x"),N(e,"y"),N(e,"z"));
    internal static object Context()=>new {tap_target=Tap.Host.CurrentTapTarget(),middle_confirm=new{Middle.PluginRuntime.Enabled,Middle.PluginRuntime.IsRunning,Middle.PluginRuntime.LastError,settings_path=Middle.Preferences.FilePath}};
    public static PorscheBinding Prepare(JsonElement q,string directory)
    {
        var c=q.GetProperty("parameters");string action=S(q,"action");var b=new PorscheBinding();
        if(action is "drilling.stages" or "drilling.tap") {
            bool tapping=action=="drilling.tap";
            var request=new Tap.Request{Metric=SettingsManager.Metric,Sets=c.GetProperty("sets").EnumerateArray().Select(set=>new Tap.HoleSet{
                Name=S(set,"name"),Plane=Tap.Host.DescribePlane(I(set,"reference_id")),Top=N(set,"top"),
                LocalPoints=set.GetProperty("local_points").EnumerateArray().Select(V).ToArray(),Stages=set.GetProperty("stages").EnumerateArray().Select(Read<Tap.Stage>).ToArray()
            }).ToArray()};
            if(tapping!=request.Sets.Any(set=>set.Stages.Any(s=>s.Purpose==Tap.StagePurpose.Tap)))throw new ArgumentException("Tapping action/purpose mismatch.");
            var plan=Tap.Rules.Plan(request);Tap.Rules.RequireExecutable(plan);
            // The original drill contract lacks tap-only fields. Strip those two known fields,
            // rather than passing extra fields through its strict deserializer.
            var json=JsonSerializer.SerializeToNode(request,Json);
            if(!tapping)foreach(var set in json["Sets"].AsArray())foreach(var stage in set["Stages"].AsArray()){stage.AsObject().Remove("ThreadPitch");stage.AsObject().Remove("TapTarget");}
            Tap.Batch tap=null;Ad.Batch drill=null;
            if(tapping)tap=Tap.Host.Prepare(request,directory);else drill=Ad.Host.PrepareJson(json.ToJsonString(),directory);
            b.Preview=new{action,plan,creates_operations=plan.Length,existing_tools_only=true,regenerates=false,posting=false,feed_contract="Explicit raw values; no inferred feed mode or RPM/pitch conversion"};
            b.Apply=()=>{if(tapping)tap.Apply();else drill.Apply();};
            b.Rollback=()=>{if(tapping)tap.Rollback();else drill.Rollback();};
            b.Readback=()=>JsonDocument.Parse(tapping?tap.AuditJson:drill.AuditJson).RootElement.Clone();
        } else if(action=="geometry.convex_boundary") {
            int id=I(q,"source_id");var v=V(c.GetProperty("origin"));
            var request=new Boundary.BoundaryRequest(id,new(v.X,v.Y,v.Z),N(c,"depth"),N(c,"tolerance"),I(c,"output_level"),c.GetProperty("clockwise").GetBoolean());
            if(!LevelsManager.IsLevelVisible(request.OutputLevel))throw new ArgumentException("Existing visible output level required.");
            Boundary.BoundaryReceipt Selected(bool create){using var selection=new GeometrySelection();GeometrySelection.Set(new[]{id});return create?Boundary.NativeBoundary.Create(request):Boundary.NativeBoundary.Preview(request);}
            var preview=Selected(false);Boundary.BoundaryReceipt result=null;string before=PorscheBindings.DatabaseStamp(),after=null;
            b.Preview=new{action,request,preview.Boundary,preview.Contract,scope="One certified convex planar polyhedron, world XY, one closed loop"};
            b.Apply=()=>{result=Selected(true);if(!result.Committed)throw new InvalidOperationException("Boundary not committed.");after=PorscheBindings.DatabaseStamp();};
            b.Rollback=()=>{if(after!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Database changed after boundary creation.");PorscheBindings.DeleteGeometry(result.GeometryIds);if(before!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Boundary rollback baseline mismatch.");};
            b.Readback=()=>new{created_geometry_ids=result?.GeometryIds??Array.Empty<int>(),boundary=result?.Boundary,committed=result?.Committed};
        } else if(action=="interface.middle_confirm") {
            string path=Middle.Preferences.FilePath;byte[] before=File.Exists(path)?File.ReadAllBytes(path):null;
            bool running=Middle.PluginRuntime.IsRunning,enabled=Middle.PluginRuntime.Enabled;
            var original=before==null?new Middle.Settings():JsonSerializer.Deserialize<Middle.Settings>(before,Json);original.Validate();if(before!=null&&!JsonDocument.Parse(before).RootElement.TryGetProperty("Enabled",out _))throw new ArgumentException("Settings must explicitly specify Enabled.");if(original.Enabled!=enabled||running&&!enabled)throw new ArgumentException("Settings/runtime are inconsistent; resolve observer state before editing.");
            var next=new Middle.Settings{Enabled=c.GetProperty("enabled").GetBoolean(),MaximumClickMilliseconds=I(c,"maximum_click_milliseconds")};next.Validate();byte[] after=null;
            void Atomic(byte[] value){if(value==null){if(File.Exists(path))File.Delete(path);return;}Directory.CreateDirectory(Path.GetDirectoryName(path));var temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";try{File.WriteAllBytes(temp,value);File.Move(temp,path,true);}finally{if(File.Exists(temp))File.Delete(temp);}}
            bool Same(byte[] value)=>value==null?!File.Exists(path):File.Exists(path)&&File.ReadAllBytes(path).SequenceEqual(value);
            void Restore(){Middle.PluginRuntime.Stop();Atomic(before);Middle.PluginRuntime.Start();if(!running)Middle.PluginRuntime.Stop();if(Middle.PluginRuntime.Enabled!=enabled||Middle.PluginRuntime.IsRunning!=running||!Same(before))throw new InvalidOperationException("Middle-confirm state restoration mismatch.");}
            b.Preview=new{action,path,before_file_exists=before!=null,before_enabled=enabled,before_running=running,settings=next,scope="Configure own observer only; does not click or accept any dialog"};
            b.Apply=()=>{if(!Same(before))throw new InvalidOperationException("Settings changed before apply.");try{Middle.PluginRuntime.Stop();Atomic(System.Text.Encoding.UTF8.GetBytes(Encode(next)));Middle.PluginRuntime.Start();if(Middle.PluginRuntime.Enabled!=next.Enabled||Middle.PluginRuntime.IsRunning!=next.Enabled)throw new InvalidOperationException("Middle-confirm runtime mismatch.");after=File.ReadAllBytes(path);}catch{Restore();throw;}};
            b.Rollback=()=>{if(!Same(after)||Middle.PluginRuntime.Enabled!=next.Enabled||Middle.PluginRuntime.IsRunning!=next.Enabled)throw new InvalidOperationException("Middle-confirm changed after apply.");Restore();};
            b.Readback=()=>new{Middle.PluginRuntime.Enabled,Middle.PluginRuntime.IsRunning,settings=File.Exists(path)?JsonDocument.Parse(File.ReadAllText(path)).RootElement.Clone():(JsonElement?)null};
        } else throw new ArgumentException("Unknown panel-derived action: "+action);
        return b;
    }
}
