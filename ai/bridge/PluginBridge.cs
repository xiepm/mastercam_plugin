using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using Mastercam.Database;
using Mastercam.Database.Types;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Operations;
using MPRebuild2027.Core;
using Ops = OperationTools2027;
using Hsm = HSMRebuild2027;
using Mp = MPRebuild2027;

[assembly:System.Reflection.AssemblyVersion("1.1.0.0")]
[assembly:System.Runtime.Versioning.TargetFramework(".NETCoreApp,Version=v10.0")]
namespace MastercamPluginAI;

public static class Bridge
{
    public static void CheckAssembly(string file,string hash)
    {
        if(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file)))!=hash)throw new InvalidOperationException("Dependency hash changed: "+file);
        var a=Assembly.LoadFrom(file);
        using var stream=File.OpenRead(file);using var pe=new PEReader(stream);var md=pe.GetMetadataReader();
        if(a.ManifestModule.ModuleVersionId!=md.GetGuid(md.GetModuleDefinition().Mvid))throw new InvalidOperationException("Loaded assembly differs from disk; restart Mastercam: "+file);
    }
    static readonly JsonSerializerOptions Json = new() { IncludeFields=true, WriteIndented=true, Converters={new JsonStringEnumConverter()}, UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow };
    static readonly Dictionary<string,Plan> Plans = new();
    static readonly string Session = Guid.NewGuid().ToString("N");
    sealed class Plan
    {
        public string Id=Guid.NewGuid().ToString("N"), State="Prepared", Hash, Baseline, FileStamp, Document, Action, Error;
        public DateTime PreparedAt=DateTime.UtcNow;
        public JsonElement Request;
        public object Preview;
        public PreviewGuard Approval;
        public Action Apply, Rollback, Regenerate;
        public Func<object> Readback;
    }
    static string Write(object value)=>JsonSerializer.Serialize(value,Json);
    static string Hash(string s)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(s)));
    static T Read<T>(JsonElement e)=>JsonSerializer.Deserialize<T>(e.GetRawText(),Json);
    static int[] Ids(JsonElement p,string key)=>p.GetProperty(key).EnumerateArray().Select(v=>v.GetInt32()).ToArray();
    static double N(JsonElement p,string key)=>p.GetProperty(key).GetDouble();
    static Vec3 V(JsonElement p)=>new(N(p,"x"),N(p,"y"),N(p,"z"));
    static Geometry[] Geometry()=>SearchManager.GetGeometry(new SelectionMask(true,false,false)).Concat(SearchManager.GetGeometry(new SelectionMask(false,false,true))).GroupBy(g=>g.GetEntityID()).Select(g=>g.First()).OrderBy(g=>g.GetEntityID()).ToArray();
    static string FileStamp() { var f=new FileInfo(FileManager.CurrentFileName); return f.Exists?f.Length+":"+f.LastWriteTimeUtc.Ticks:"unsaved"; }
    static object Frame(Mastercam.Database.MCView v)=>new{v.ViewID,v.ViewNumber,v.ViewOrigin,v.ViewMatrix};
    static string Snapshot()=>Hash(Write(new {
        file=FileManager.CurrentFileName,metric=SettingsManager.Metric,context=Mp.HostSession.Context(),
        geometry=Geometry().Select(g=>new{id=g.GetEntityID(),g.TimeStamp,g.Selected,g.Blanked,g.Color,g.Level}),
        operations=SearchManager.GetOperations().OrderBy(o=>o.GetOperationID()).Select(o=>new{id=o.GetOperationID(),o.TimeStamp,o.Name,o.Dirty,o.Posting,tool=o.OperationTool?.Slot,frame=Frame(o.ToolPlane)}),
        selection=SearchManager.GetOperationIDs(false).OrderBy(i=>i),
        tools=SearchManager.GetTools().OrderBy(t=>t.Slot).Select(t=>new{t.Slot,t.Number,t.Name,t.Diameter,t.Length,t.FluteLength,t.TipAngle,t.LengthOffset,t.DiameterOffset})
    }));
    static object Inspect()=>new {
        session_id=Session,process_id=Environment.ProcessId,document=FileManager.CurrentFileName,metric=SettingsManager.Metric,api=typeof(Geometry).Assembly.FullName,
        geometry_count=Geometry().Length,geometry=Geometry().Take(250).Select(g=>new{id=g.GetEntityID(),type=g.GetType().Name,g.Level,g.Color,g.Selected,g.Blanked,g.TimeStamp}),
        operations=SearchManager.GetOperations().Select(o=>new{id=o.GetOperationID(),o.Name,type=o.GetType().Name,o.Dirty,o.Posting,tool_slot=o.OperationTool?.Slot,tool_plane=Frame(o.ToolPlane)}),
        selected_operation_ids=SearchManager.GetOperationIDs(false),
        views=SearchManager.GetViews().Select(v=>new{v.ViewID,v.ViewNumber,v.ViewName,frame=Frame(v)}),
        visible_occupied_levels=Geometry().Select(g=>g.Level).Distinct().Where(LevelsManager.IsLevelVisible).OrderBy(x=>x),
        selected_solid_ids=Geometry().Where(g=>g is SolidGeometry&&g.Selected).Select(g=>g.GetEntityID()),
        tools=SearchManager.GetTools().Select(t=>new{slot=t.Slot,number=t.Number,name=t.Name,type=t.GetType().Name,diameter=t.Diameter,t.TipAngle,t.PilotDia,t.Length,t.FluteLength,t.ShoulderLength,t.ShankDia,t.Flutes,t.LengthOffset,t.DiameterOffset,t.IsMetric})
    };
    static object View(Plan p)=>new {plan_id=p.Id,session_id=Session,action=p.Action,status=p.State,document=p.Document,preview_sha256=p.Hash,prepared_at_utc=p.PreparedAt,error=p.Error,preview=p.Preview,result=p.Readback?.Invoke()};
    static void Document(JsonElement q) {
        string expected=q.GetProperty("expected_document").GetString();
        if(string.IsNullOrWhiteSpace(expected)||!File.Exists(expected)||!string.Equals(Path.GetFullPath(expected),Path.GetFullPath(FileManager.CurrentFileName),StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Expected saved document does not match active document.");
    }
    static void Bind(Plan p,string directory)
    {
        var q=p.Request;var c=q.GetProperty("parameters");
        switch(p.Action) {
        case "porsche.project_boundary":case "porsche.contour":case "porsche.heal_holes":case "porsche.holes": {
            var binding=PorscheBindings.Prepare(q,directory);
            p.Preview=binding.Preview;p.Apply=binding.Apply;p.Rollback=binding.Rollback;p.Readback=binding.Readback;break;
        }
        case "operation.depth": case "operation.finish": case "operation.chamfer": {
            int[] ids=Ids(q,"operation_ids");
            Ops.PreparedChange change=p.Action switch {
                "operation.depth"=>Ops.Host.PrepareDepth(ids,Read<Ops.DepthConfig>(c)),
                "operation.finish"=>Ops.Host.PrepareFinish(ids,Read<Ops.FinishConfig>(c)),
                _=>Ops.Host.PrepareChamfer(ids,Read<Ops.ChamferConfig>(c))};
            p.Preview=JsonDocument.Parse(Ops.Json.Write(new{change.Batch.Purpose,change.Batch.Plan,change.Batch.Edits})).RootElement.Clone();
            p.Apply=change.Apply;p.Rollback=change.Batch.Rollback;p.Readback=()=>JsonDocument.Parse(Ops.Json.Write(change.Batch)).RootElement.Clone();break;
        }
        case "hsm.pocket": {
            int id=q.GetProperty("reference_id").GetInt32();
            var op=SearchManager.GetOperation(id) as ChainBasedOperation??throw new InvalidOperationException("Reference must be chain based.");
            // Preserve the complete native-backed list. Never filter/Take a Chain[].
            var chains=op.GetChainArray();
            var change=Hsm.Host.Prepare(id,chains,Read<Hsm.PocketSettings>(c));
            p.Preview=new{reference_id=id,parameters=change.Settings,boundary=Hsm.Host.ChainInfo(chains),observations=change.Observations};
            p.Apply=change.Apply;p.Rollback=change.Rollback;p.Regenerate=change.Regenerate;
            p.Readback=()=>JsonDocument.Parse(Hsm.Json.Write(change)).RootElement.Clone();break;
        }
        case "mp.sections": case "mp.draft": {
            Mp.Dependencies.Ensure();Mp.AnalysisPlan change;
            int[] ids=Ids(q,"solid_ids");
            if(p.Action=="mp.sections") change=Mp.Workflows.Sections(ids,V(c.GetProperty("origin")),V(c.GetProperty("normal")),c.GetProperty("count").GetInt32(),N(c,"spacing"),N(c,"mesh_tolerance"),N(c,"weld_tolerance"),directory);
            else change=Mp.Workflows.Draft(ids,V(c.GetProperty("pull")),N(c,"threshold_degrees"),N(c,"mesh_tolerance"),N(c,"weld_tolerance"),c.GetProperty("transition_edges").GetBoolean(),c.GetProperty("normal_glyphs").GetBoolean(),N(c,"glyph_length"),c.GetProperty("maximum_glyphs").GetInt32(),directory);
            int level=q.GetProperty("output_level").GetInt32();
            if(!LevelsManager.IsLevelVisible(level))throw new InvalidOperationException("Output level must already exist and be visible.");
            Mp.OutputRun output=null;
            p.Preview=new{change.Kind,change.Summary,line_count=change.Lines.Length,output_level=level,change.Parameters,boundary=Mp.Workflows.Boundary};
            p.Apply=()=>output=Mp.Workflows.Create(change,level);
            p.Rollback=()=>{if(output==null)throw new InvalidOperationException("No created output.");output.Rollback();};
            p.Readback=()=>new{analysis_path=change.ReportPath,created_ids=output?.CreatedIds??Array.Empty<int>()};break;
        }
        default:throw new ArgumentException("Unsupported typed action: "+p.Action);
        }
    }
    public static void RunFile(string requestPath,string resultPath)
    {
        // A durable result is authoritative; never repeat a completed request.
        if(File.Exists(resultPath))return;
        object result;
        try {
            var q=JsonDocument.Parse(File.ReadAllText(requestPath)).RootElement;
            string command=q.GetProperty("command").GetString();
            object data;
            if(command=="inspect") data=Inspect();
            else if(command=="information") {
                Document(q);var reach=q.TryGetProperty("reach",out var r)&&r.ValueKind!=JsonValueKind.Null?Read<Ops.ReachConfig>(r):null;
                data=Ops.Host.Information(Ids(q,"operation_ids"),reach);
            } else if(command=="prepare") {
                Document(q);if(Plans.Values.Count(p=>p.State=="Prepared")>=20)throw new InvalidOperationException("Too many pending plans; discard old plans first.");
                var p=new Plan{Request=q.Clone(),Document=FileManager.CurrentFileName,FileStamp=FileStamp(),Baseline=Snapshot(),Action=q.GetProperty("action").GetString()};
                Bind(p,q.GetProperty("artifact_directory").GetString());
                if(Snapshot()!=p.Baseline)throw new InvalidOperationException("Preparation changed database/selection; inspect before continuing.");
                p.Approval=new PreviewGuard(Write(p.Preview));
                p.Hash=Hash(q.GetRawText()+p.Approval.Approved+p.Baseline);Plans.Add(p.Id,p);data=View(p);
            } else {
                string id=q.GetProperty("plan_id").GetString();
                if(!Plans.TryGetValue(id,out var p))throw new InvalidOperationException("Plan is unavailable in this Mastercam process. Prepare again; never replay old apply.");
                if(command=="plan_status")data=View(p);
                else if(command=="discard") {if(p.State!="Prepared")throw new InvalidOperationException("Only prepared plans can be discarded.");p.State="Discarded";p.Apply=null;p.Rollback=null;data=View(p);}
                else {
                    Document(q);
                    if(!string.Equals(p.Document,FileManager.CurrentFileName,StringComparison.OrdinalIgnoreCase)||p.FileStamp!=FileStamp())throw new InvalidOperationException("Document or saved file changed. Plan invalidated.");
                    if(command=="apply") {
                        if(p.State!="Prepared")throw new InvalidOperationException("Plan is not Prepared; inspect existing result instead of retrying.");
                        if(q.GetProperty("preview_sha256").GetString()!=p.Hash)throw new InvalidOperationException("Preview hash mismatch.");
                        if(DateTime.UtcNow-p.PreparedAt>TimeSpan.FromMinutes(15)||Snapshot()!=p.Baseline)throw new InvalidOperationException("Plan expired or source/context changed; prepare again.");
                        // Rebuild native wrappers immediately before writing, avoiding stale handles after a reload.
                        Plan candidate;
                        try {
                            candidate=p.Approval.Rebuild(()=>{
                                var next=new Plan{Request=p.Request,Action=p.Action};
                                Bind(next,q.GetProperty("artifact_directory").GetString());
                                if(Snapshot()!=p.Baseline)throw new InvalidOperationException("Rebuild changed database/selection; inspect before continuing.");
                                return next;
                            },next=>Write(next.Preview));
                        } catch(Exception e) {
                            p.State="Invalidated";p.Error=e.ToString();p.Apply=null;p.Rollback=null;p.Regenerate=null;
                            throw;
                        }
                        p.Apply=candidate.Apply;p.Rollback=candidate.Rollback;p.Regenerate=candidate.Regenerate;p.Readback=candidate.Readback;
                        p.State="Applying";
                        try{p.Apply();p.State="Applied";}catch(Exception e){p.State="Failed";p.Error=e.ToString();throw;}
                    } else if(command=="rollback") {
                        if(p.State!="Applied"&&p.State!="Regenerated"&&p.State!="RegenerationFailed")throw new InvalidOperationException("Plan cannot be rolled back from "+p.State);
                        try{p.Rollback();p.State="RolledBack";}catch(Exception e){p.State="RollbackFailed";p.Error=e.ToString();throw;}
                    } else if(command=="regenerate") {
                        if(p.State!="Applied"||p.Regenerate==null)throw new InvalidOperationException("Only an applied HSM plan supports this regeneration endpoint.");
                        try{p.Regenerate();p.State="Regenerated";}catch(Exception e){p.State="RegenerationFailed";p.Error=e.ToString();throw;}
                    } else throw new ArgumentException("Unknown command.");
                    data=View(p);
                }
            }
            result=new{ok=true,session_id=Session,data};
        }catch(Exception e){result=new{ok=false,session_id=Session,error=e.ToString()};}
        File.WriteAllText(resultPath+".tmp",Write(result));File.Move(resultPath+".tmp",resultPath);
    }
}
