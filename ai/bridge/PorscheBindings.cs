using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Mastercam.Database;
using Mastercam.Database.Types;
using Mastercam.Operations;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Tools;
using PorscheAdvanced2027;
using AdvancedDrillGeometryContract;

namespace MastercamPluginAI;

public sealed class PorscheBinding
{
    public object Preview;
    public Action Apply,Rollback;
    public Func<object> Readback;
}

public static class PorscheBindings
{
    static readonly JsonSerializerOptions Json=new(){IncludeFields=true,WriteIndented=true,Converters={new JsonStringEnumConverter()},UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    static string Write(object x)=>JsonSerializer.Serialize(x,Json);
    static string Hash(object x)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Write(x))));
    static T Read<T>(JsonElement e)=>JsonSerializer.Deserialize<T>(e.GetRawText(),Json);
    internal static object Shape(int id) {
        // API29 face-map queries can clear selection even though they only read topology.
        using var selection=new GeometrySelection();
        var g=Geometry.RetrieveEntity(id)??throw new InvalidOperationException("Object disappeared: "+id);
        return new{id,g.TimeStamp,g.Level,g.Color,g.Blanked,normal=g is SurfaceGeometry surf?(bool?)surf.IsNormalReversed:null,type=g.GetType().FullName,
            faces=g is SolidGeometry?SearchManager.GetFaceTagsAndPidMapFromBodyEntity(id).OrderBy(x=>x.Key).Select(x=>new{x.Key,x.Value}).ToArray():null,
            line=g is Mastercam.Curves.LineGeometry l?new{a=BoundaryHost.V(l.EndPoint1),b=BoundaryHost.V(l.EndPoint2)}:null};
    }
    internal static object DatabaseFacts()=>new {
        geometry=GeometrySelection.All().OrderBy(g=>g.GetEntityID()).Select(g=>Shape(g.GetEntityID())),
        ops=SearchManager.GetOperations().OrderBy(o=>o.GetOperationID()).Select(o=>new{id=o.GetOperationID(),o.TimeStamp,o.Name,o.NCIName,o.Dirty,o.Posting,tool=o.OperationTool?.Slot}),
        tools=SearchManager.GetTools().OrderBy(t=>t.Slot).Select(HoleHost.ToolState),
        planes=SearchManager.GetViews().OrderBy(v=>v.ViewID).Select(HoleHost.PlaneState)
    };
    internal static string DatabaseStamp()=>Hash(DatabaseFacts());
    static object CurrentOperations(IEnumerable<int> ids)=>ids.Select(id=>new{id,exists=SearchManager.GetOperationData(id)?.IsValid==true,state=SearchManager.GetOperationData(id)?.IsValid==true?HoleHost.OperationState(id):null}).ToArray();
    static MCView Plane(int id)=>SearchManager.GetViews().SingleOrDefault(v=>v.ViewID==id)??throw new ArgumentException("Unknown ViewID; use mc_inspect.views.");
    static void SourceCheck(int[] ids) {
        if(ids.Length==0||ids.Distinct().Count()!=ids.Length)throw new ArgumentException("Unique solid IDs required.");
        foreach(int id in ids)if(Geometry.RetrieveEntity(id) is not SolidGeometry g||g.Blanked||!LevelsManager.IsLevelVisible(g.Level))throw new ArgumentException("Visible solid required: "+id);
    }
    static Operation Reference(int id,bool contour) {
        var op=SearchManager.GetOperation(id)??throw new ArgumentException("Reference operation missing.");
        if(op.Locked||SearchManager.GetOperationData(id).MachineGroupID!=GroupManager.GetActiveMachineGroup()?.ID)throw new ArgumentException("Reference must be unlocked and in the active machine group.");
        if(contour&&(op is not ContourOperation c||c.CutParams.ContourSubtype!=Mastercam.Operations.Types.ContourSubtypeType.Basic||op.OperationTool is not EndMillFlatTool))throw new ArgumentException("Reference must be Basic 2D contour with flat end mill.");
        return op;
    }
    static object ProjectionPreview(ProjectionResult p)=>new{p.MinimumZ,p.MaximumZ,p.Tolerance,p.MeshTriangles,loop_count=p.Loops.Length,
        loops=p.Loops.Select((l,i)=>new{index=i,l.IsHole,l.SignedArea,point_count=l.Points.Length}),coordinate_sha256=Hash(p)};
    static QueryOptions HealingQuery()=>new(GetHolesMethod.ByDetection,new(0,0,1),0,1000000,false,false,true,true,10000,1000);
    static HoleFact[] Targets(HoleReadback facts,double min,double max)=>facts.Holes.Where(h=>h.Segments.Any(s=>s.ApiType=="Cylinder")&&h.Segments.Where(s=>s.ApiType=="Cylinder").Min(s=>s.StartRadius)>=min&&h.Segments.Where(s=>s.ApiType=="Cylinder").Min(s=>s.StartRadius)<=max).ToArray();
    internal static void DeleteGeometry(IEnumerable<int> ids) {
        foreach(int id in ids.Reverse()){var g=Geometry.RetrieveEntity(id);if(g==null||!g.Delete())throw new InvalidOperationException("Owned geometry deletion failed: "+id);}
    }
    public static PorscheBinding Prepare(JsonElement q,string directory)
    {
        Directory.CreateDirectory(directory);
        string action=q.GetProperty("action").GetString();var c=q.GetProperty("parameters");
        int[] ids=q.GetProperty("solid_ids").EnumerateArray().Select(x=>x.GetInt32()).ToArray();SourceCheck(ids);
        string sources=Hash(ids.Select(Shape));var binding=new PorscheBinding();
        Action apply=null,rollback=null;Func<object> result=null;
        if(action=="porsche.project_boundary"||action=="porsche.contour") {
            var plane=Plane(q.GetProperty("plane_id").GetInt32());var frame=BoundaryHost.FrameOf(plane);frame.Validate();
            bool machining=action=="porsche.contour";double tolerance=c.GetProperty(machining?"Tolerance":"tolerance").GetDouble();
            int level=c.GetProperty(machining?"OutputLevel":"output_level").GetInt32();
            if(!LevelsManager.IsLevelVisible(level))throw new ArgumentException("Output level must already exist and be visible.");
            BoundarySettings settings=machining?Read<BoundarySettings>(c):null;
            int reference=machining?q.GetProperty("reference_id").GetInt32():0;
            if(machining){settings.Validate();Reference(reference,true);if(!settings.FeedModeReviewed||!q.GetProperty("allow_create_tools").GetBoolean())throw new ArgumentException("Review feed mode and permit missing-tool creation.");}
            var projection=BoundaryHost.Analyze(ids,frame,tolerance,directory);
            if(projection.Loops.Length==0||projection.Loops.Sum(l=>l.Points.Length)>10000)throw new ArgumentException("Empty or oversized projection; choose a suitable tolerance.");
            double height=machining?projection.MaximumZ:c.GetProperty("height").ValueKind==JsonValueKind.Null?projection.MaximumZ:c.GetProperty("height").GetDouble();
            if(machining){double bottom=settings.UseModelBottom?projection.MinimumZ:settings.Bottom;if(bottom>=projection.MaximumZ||projection.MaximumZ-bottom>settings.FluteLength)throw new ArgumentException("Bottom must be below top and within configured flute length.");}
            binding.Preview=new{action,source_ids=ids,source_sha256=sources,plane_id=plane.ViewID,frame,projection=ProjectionPreview(projection),height,output_level=level,parameters=c,
                reference_id=reference,creates_operations=machining?3:0,may_create_tools=machining,regenerates=machining&&settings.Regenerate,
                tool_inventory=machining?SearchManager.GetTools().OrderBy(t=>t.Slot).Select(HoleHost.ToolState).ToArray():null};
            if(machining) {
                BoundaryRun run=null;
                apply=()=>run=BoundarySequence.Apply(ids,plane,reference,settings,directory);
                rollback=()=>run.Rollback();
                result=()=>new{created_operation_ids=run?.Created.Operations.ToArray()??Array.Empty<int>(),created_tool_slots=run?.Created.Tools.ToArray()??Array.Empty<int>(),created_geometry_ids=run?.Output.CurveIds.SelectMany(x=>x).ToArray()??Array.Empty<int>(),native_audit=run?.Created.AuditPath,native_readbacks=run?.Created.Readbacks,operations=CurrentOperations(run?.Created.Operations??new List<int>())};
            } else {
                BoundaryOutput output=null;
                apply=()=>output=BoundaryHost.CreateCurves(projection,frame,height,level);
                rollback=()=>DeleteGeometry(output.CurveIds.SelectMany(x=>x));
                result=()=>new{created_geometry_ids=output?.CurveIds.SelectMany(x=>x).ToArray()??Array.Empty<int>(),curve_groups=output?.CurveIds};
            }
        } else if(action=="porsche.holes") {
            var settings=Read<HoleSettings>(c);settings.Validate();var a=q.GetProperty("alignment");var alignment=new V3(a.GetProperty("x").GetDouble(),a.GetProperty("y").GetDouble(),a.GetProperty("z").GetDouble());
            int reference=q.GetProperty("reference_id").GetInt32();Reference(reference,false);
            var plans=HoleHost.Recognize(ids,alignment,settings);if(plans.Length==0)throw new ArgumentException("No supported holes in the diameter interval.");
            binding.Preview=new{action,source_ids=ids,source_sha256=sources,reference_id=reference,alignment,parameters=c,hole_count=plans.Length,operation_count=plans.Sum(p=>p.Stages.Length),plans,
                tool_inventory=SearchManager.GetTools().OrderBy(t=>t.Slot).Select(HoleHost.ToolState),may_create_tools=settings.CreateMissingTools,may_create_axis_planes=true,regenerates=settings.Regenerate};
            HoleRun run=null;apply=()=>run=HoleHost.Apply(plans,settings,reference,directory);rollback=()=>run.Rollback();
            result=()=>new{created_operation_ids=run?.Operations.ToArray()??Array.Empty<int>(),created_tool_slots=run?.Tools.ToArray()??Array.Empty<int>(),created_plane_ids=run?.Planes.ToArray()??Array.Empty<int>(),native_audit=run?.AuditPath,native_readbacks=run?.Readbacks,operations=CurrentOperations(run?.Operations??new List<int>())};
        } else if(action=="porsche.heal_holes") {
            double min=c.GetProperty("minimum_radius").GetDouble(),max=c.GetProperty("maximum_radius").GetDouble();
            if(!double.IsFinite(min)||!double.IsFinite(max)||min<0||max<=min)throw new ArgumentException("Invalid radius interval.");
            HoleReadback[] facts;
            using(var selection=new GeometrySelection())facts=ids.Select(id=>HoleFactsReader.ReadFromBody(id,HealingQuery())).ToArray();
            var targets=facts.Select(f=>new{source_id=f.SolidId,holes=Targets(f,min,max)}).ToArray();
            if(targets.Any(t=>t.holes.Length==0))throw new ArgumentException("Every selected solid must contain a complete hole in the radius interval.");
            binding.Preview=new{action,source_ids=ids,source_sha256=sources,minimum_radius=min,maximum_radius=max,targets,output_policy="independent copies; original bodies preserved",native_result_pending=true};
            var outputs=new List<HealingResult>();
            apply=()=>{
                try{foreach(int id in ids)outputs.Add(HoleHealing.CreateHealedFaceCopy(id,min,max));}
                catch(Exception failure){try{DeleteGeometry(outputs.Select(o=>o.OutputId));outputs.Clear();}catch(Exception cleanup){throw new AggregateException("Healing failed and owned-copy cleanup failed.",failure,cleanup);}throw;}
            };
            rollback=()=>DeleteGeometry(outputs.Select(o=>o.OutputId));
            result=()=>new{created_geometry_ids=outputs.Select(o=>o.OutputId).ToArray(),outputs,output_exists=outputs.Select(o=>new{o.OutputId,exists=Geometry.RetrieveEntity(o.OutputId)!=null})};
        } else throw new ArgumentException("Unknown Porsche action.");
        string status="Prepared",after=null,before=DatabaseStamp(),audit=Path.Combine(directory,"porsche-adapter.json");
        void SourceUnchanged(){if(Hash(ids.Select(Shape))!=sources)throw new InvalidOperationException("Source solid changed; inspect native audit.");}
        object Readback()=>new{status,source_preserved=Hash(ids.Select(Shape))==sources,audit_path=audit,output=result()};
        void Save()=>File.WriteAllText(audit,Write(Readback()));
        SourceUnchanged();File.WriteAllText(Path.Combine(directory,"preview.json"),Write(binding.Preview));
        binding.Apply=()=>{
            try{SourceUnchanged();apply();SourceUnchanged();after=DatabaseStamp();status="Applied";Save();}
            catch{status="Failed";Save();throw;}
        };
        binding.Rollback=()=>{
            if(status!="Applied"||after!=DatabaseStamp())throw new InvalidOperationException("Database changed after this run; rollback refused before deleting owned objects.");
            rollback();SourceUnchanged();if(before!=DatabaseStamp())throw new InvalidOperationException("Rollback inventory differs from baseline.");status="RolledBack";Save();
        };
        binding.Readback=Readback;return binding;
    }
}
