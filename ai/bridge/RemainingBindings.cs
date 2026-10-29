using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Mastercam.Database;
using Mastercam.Curves;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Operations;
using PorscheAdvanced2027;
using Geo=MastercamPluginAI.GeometryAdapter;
using Materials=LittleBee.Rebuilt.Materials;
namespace MastercamPluginAI;
public static class RemainingBindings
{
    static readonly JsonSerializerOptions Json=new(){IncludeFields=true,Converters={new JsonStringEnumConverter()},UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    static string Encode(object v)=>JsonSerializer.Serialize(v,Json);
    static T Read<T>(JsonElement e)=>JsonSerializer.Deserialize<T>(e.GetRawText(),Json);
    static int I(JsonElement e,string k)=>e.GetProperty(k).GetInt32();
    static int[] Ids(JsonElement e,string k)=>e.GetProperty(k).EnumerateArray().Select(x=>x.GetInt32()).ToArray();
    static string S(JsonElement e,string k)=>e.GetProperty(k).GetString();
    static string Sha(string path)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
    static (Mastercam.Support.Types.ExternalGroupsFileData[] groups,Mastercam.Support.Types.ExternalOpsFileData[] ops) Library(string path){var groups=Array.Empty<Mastercam.Support.Types.ExternalGroupsFileData>();var ops=Array.Empty<Mastercam.Support.Types.ExternalOpsFileData>();if(!SearchManager.GetOpGroupDataInExternalFile(path,ref groups,ref ops)||ops==null)throw new InvalidDataException("Native operation library read failed.");return(groups,ops);}
    public static object LibraryInfo(string path){if(!Path.IsPathFullyQualified(path)||!path.EndsWith(".mcam-operations",StringComparison.OrdinalIgnoreCase)||!File.Exists(path))throw new ArgumentException("Existing absolute .mcam-operations path required.");var r=Library(path);return new{path,sha256=Sha(path),groups=r.groups.Select(g=>new{g.ID,g.Name}),operations=r.ops.Select(o=>new{id=o.OpIdn,o.Name,o.OpCode,o.ParentID,tool=o.OpTool==null?null:new{o.OpTool.Number,o.OpTool.Diameter,o.OpTool.ToolTypeID}})};}
    public static object EntityInfo(int[] ids){using var selection=new GeometrySelection();return ids.Select(id=>{var g=Geometry.RetrieveEntity(id)??throw new ArgumentException("Missing entity "+id);object[] edges=Array.Empty<object>();if(g is SolidGeometry){var faces=Geo.HostGeometry.Faces(id);edges=Geo.EdgeTopology.Index(Geo.HostGeometry.FaceEdges(faces)).SelectMany(e=>e.Value.Select(tag=>(object)new{tag,incident_face_pids=e.Key,unique=e.Value.Length==1})).ToArray();}return new{id,type=g.GetType().Name,g.Level,g.Color,g.TimeStamp,edges};}).ToArray();}
    public static PorscheBinding Prepare(JsonElement q,string directory)
    {
        Directory.CreateDirectory(directory);
        using var preparationSelection=new GeometrySelection();
        var c=q.GetProperty("parameters");string action=S(q,"action");var b=new PorscheBinding();
        if(action=="selection.chains"){
            int[] ids=Ids(q,"entity_ids"),before=GeometrySelection.Selected();foreach(int id in ids){var g=Geometry.RetrieveEntity(id);if(g is not LineGeometry&&g is not ArcGeometry&&g is not NURBSCurveGeometry||g.Blanked||!LevelsManager.IsLevelVisible(g.Level))throw new ArgumentException("Visible line/arc/NURBS curve required: "+id);}
            object[] info;string baseline=PorscheBindings.DatabaseStamp();var owned=new List<int>();Chain[] chains=null;
            using(var selection=new GeometrySelection()){
                try{
                    GeometrySelection.Set(ids);var copy=FixtureAdapter.NativeFixtureCopy.PlaceSelected(new(0,0,0),new(0,0,0),new(0,0,0),0);owned.AddRange(copy.CreatedIds);if(copy.Status!="committed"||copy.RequiresHostReview)throw new InvalidOperationException("Temporary curve copy failed.");var map=copy.Copies.ToDictionary(x=>x.CopyId,x=>x.SourceId);
                    GeometrySelection.Set(Array.Empty<int>());
                    chains=ChainManager.ChainGeometry(owned.Select(Geometry.RetrieveEntity).ToArray());if(chains==null||chains.Length!=I(c,"expected_chain_count")||c.GetProperty("require_closed").GetBoolean()&&chains.Any(x=>!x.IsClosed))throw new ArgumentException("Native chain count/closure differs from explicit request.");
                    var membership=chains.Select(ch=>new{ch.IsClosed,ch.Perimeter,ch.Direction,entity_ids=ChainManager.GetGeometryInChain(ch).Select(g=>map.TryGetValue(g.GetEntityID(),out int original)?original:throw new InvalidOperationException("Foreign native successor in temporary chain.")).ToArray()}).ToArray();
                    if(!membership.SelectMany(x=>x.entity_ids).Order().SequenceEqual(ids.Order()))throw new InvalidOperationException("Native chaining did not cover every input exactly once.");info=membership.Cast<object>().ToArray();
                }finally{PorscheBindings.DeleteGeometry(owned);}
            }
            if(baseline!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Temporary chain validation changed source database.");
            int[] wanted=(S(c,"mode")=="add"?before.Concat(ids):ids).Distinct().Order().ToArray();b.Preview=new{action,chains=info,selected_before=before,selected_after=wanted,validation="Native chaining on independent temporary curve copies; apply selects original entities only"};b.Apply=()=>GeometrySelection.Set(wanted);b.Rollback=()=>{if(!GeometrySelection.Selected().SequenceEqual(wanted))throw new InvalidOperationException("Selection changed after apply.");GeometrySelection.Set(before);};b.Readback=()=>new{selected_ids=GeometrySelection.Selected(),chains=info};
        }else if(action=="geometry.chamfer_edges"){
            int id=I(q,"source_id");int[] tags=Ids(c,"edge_tags");double distance=c.GetProperty("distance").GetDouble();string source=Encode(PorscheBindings.Shape(id));
            Geo.GeometryPlan Prepared(int sourceId,int[] edges){using var select=new GeometrySelection();GeometrySelection.Set(new[]{sourceId});return Geo.HostGeometry.Prepare(new[]{sourceId},new Geo.GeometryRequest{Command=Geo.GeometryCommand.ChamferEdges,EdgeTags=edges,ChamferDistance=distance});}
            var plan=Prepared(id,tags);var originalFaces=Geo.HostGeometry.Faces(id);var identities=plan.EdgeIdentities;int output=0;string after=null,before=PorscheBindings.DatabaseStamp();
            b.Preview=new{action,source_id=id,edge_tags=tags,incident_face_identities=identities,distance,output_policy="Independent solid copy; source preserved; no tangent-chain expansion"};
            b.Apply=()=>{try{var copy=SolidCopyAdapter.CopyIndependent(id);output=copy.GetEntityID();var faces=Geo.HostGeometry.Faces(output);if(!originalFaces.Select(x=>new{x.Pid,x.Type,x.Normal}).SequenceEqual(faces.Select(x=>new{x.Pid,x.Type,x.Normal})))throw new InvalidOperationException("Copy face identities do not match; edge mapping refused.");var edges=identities.Select(identity=>Geo.EdgeTopology.Resolve(identity,Geo.HostGeometry.FaceEdges(faces))).ToArray();using(var select=new GeometrySelection()){GeometrySelection.Set(new[]{output});Geo.HostGeometry.Execute(Prepared(output,edges));}if(source!=Encode(PorscheBindings.Shape(id)))throw new InvalidOperationException("Chamfer changed source.");after=PorscheBindings.DatabaseStamp();}catch{if(output>0&&Geometry.RetrieveEntity(output)!=null)PorscheBindings.DeleteGeometry(new[]{output});throw;}};
            b.Rollback=()=>{if(after!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Database changed after chamfer.");PorscheBindings.DeleteGeometry(new[]{output});if(before!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Chamfer rollback baseline mismatch.");};b.Readback=()=>new{created_id=output,exists=output>0&&Geometry.RetrieveEntity(output)!=null,source_preserved=source==Encode(PorscheBindings.Shape(id)),output_shape=output>0&&Geometry.RetrieveEntity(output)!=null?PorscheBindings.Shape(output):null};
        }else if(action=="materials.estimate"){
            var material=Read<Materials.MaterialDefinition>(c.GetProperty("material"));var stock=Read<Materials.StockItem>(c.GetProperty("stock"));var estimate=Materials.Calculate(stock,material);string path=Path.Combine(directory,"material-estimate.json");b.Preview=new{action,material,stock,estimate};b.Apply=()=>{if(File.Exists(path))throw new IOException("Output exists.");File.WriteAllText(path,Encode(new{material,stock,estimate}));};b.Rollback=()=>{};b.Readback=()=>new{estimate,path,artifact_exists=File.Exists(path),artifacts_retained=true};
        }else if(action=="operations.export"){
            File.WriteAllText(Path.Combine(directory,"database-before-export.json"),Encode(PorscheBindings.DatabaseFacts()));
            int[] ids=Ids(q,"operation_ids");bool geometry=c.GetProperty("include_geometry").GetBoolean();foreach(int id in ids)if(SearchManager.GetOperation(id)==null)throw new ArgumentException("Unknown operation.");string path=Path.Combine(directory,"operations.mcam-operations"),baseline=LibraryState.Capture();object readback=null;var selected=SearchManager.GetOperationIDs(false);
            void RestoreSelection(){OperationsManager.UnSelectAllOperations();if(selected.Length>0)OperationsManager.SelectOperations(selected.Select(SearchManager.GetOperation).ToArray());}
            b.Preview=new{action,operation_ids=ids,include_geometry=geometry,artifact_name="operations.mcam-operations",retains_file_on_rollback=true};b.Apply=()=>{try{if(File.Exists(path))throw new IOException("Output exists.");if(!OperationsManager.ExportOperations(path,"AI_EXPORTED",ids,!geometry,true)||!File.Exists(path)||new FileInfo(path).Length==0)throw new IOException("Native export failed.");if(Library(path).ops.Length!=ids.Length)throw new InvalidOperationException("Export count readback mismatch.");readback=LibraryInfo(path);File.WriteAllText(Path.Combine(directory,"database-after-export.json"),Encode(PorscheBindings.DatabaseFacts()));RestoreSelection();LibraryState.RequireEqual(baseline,LibraryState.Capture(),directory,"export-preservation");}finally{RestoreSelection();}};b.Rollback=()=>{};b.Readback=()=>new{library=readback,artifacts_retained=true};
        }else throw new ArgumentException("Unknown remaining action: "+action);
        if(action!="selection.chains"){
            var apply=b.Apply;var rollback=b.Rollback;
            b.Apply=()=>{using var selection=new GeometrySelection();apply();};
            b.Rollback=()=>{using var selection=new GeometrySelection();rollback();};
        }
        return b;
    }
}
