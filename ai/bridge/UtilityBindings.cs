using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Operations;
using PorscheAdvanced2027;
using Geo=MastercamPluginAI.GeometryAdapter;

namespace MastercamPluginAI;
public static class UtilityBindings
{
    static readonly JsonSerializerOptions Json=new(){IncludeFields=true,Converters={new JsonStringEnumConverter()},UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    static T Read<T>(JsonElement e)=>JsonSerializer.Deserialize<T>(e.GetRawText(),Json);
    static string Encode(object o)=>JsonSerializer.Serialize(o,Json);
    static T Selected<T>(int[] ids,Func<T> f){using var s=new GeometrySelection();GeometrySelection.Set(ids);return f();}
    static int[] Ids(JsonElement q,string key)=>q.GetProperty(key).EnumerateArray().Select(x=>x.GetInt32()).ToArray();
    static double N(JsonElement c,string k)=>c.GetProperty(k).GetDouble();
    static int I(JsonElement c,string k)=>c.GetProperty(k).GetInt32();
    static string S(JsonElement c,string k)=>c.GetProperty(k).GetString();
    static Operation Op(int id)=>SearchManager.GetOperation(id)??throw new ArgumentException("Operation not found: "+id);
    static void OpSelection(int[] ids){var ops=ids.Select(Op).ToArray();OperationsManager.UnSelectAllOperations();if(ops.Length>0)OperationsManager.SelectOperations(ops);if(!SearchManager.GetOperationIDs(false).Order().SequenceEqual(ids.Order()))throw new InvalidOperationException("Operation selection mismatch.");}
    public static PorscheBinding Prepare(JsonElement q,string directory)
    {
        string action=S(q,"action");var c=q.GetProperty("parameters");var b=new PorscheBinding();
        switch(action){
        case "geometry.copy_edit": {
            var ids=Ids(q,"entity_ids");var d=c.GetProperty("destination");
            var request=new Geo.GeometryRequest{Command=Enum.Parse<Geo.GeometryCommand>(S(c,"command")),Destination=new(N(d,"x"),N(d,"y"),N(d,"z")),QuarterTurns=I(c,"quarter_turns"),Color=I(c,"color"),Level=I(c,"level"),AngleTolerance=N(c,"angle_tolerance"),CurveTolerance=N(c,"curve_tolerance"),TextHeight=N(c,"text_height"),DimensionOffset=N(c,"dimension_offset"),Decimals=I(c,"decimals")};
            if(!LevelsManager.IsLevelVisible(request.Level))throw new ArgumentException("Existing visible output level required.");
            var plan=Selected(ids,()=>Geo.HostGeometry.Prepare(ids,request));
            string source=Encode(ids.Select(PorscheBindings.Shape));var owned=new List<int>();
            b.Preview=new{action,source_ids=ids,plan.Before,plan.Description,parameters=c,output_policy="edit independent copies; source IDs preserved"};
            b.Apply=()=>{
                try{
                    var copy=Selected(ids,()=>FixtureAdapter.NativeFixtureCopy.PlaceSelected(new(0,0,0),new(0,0,0),new(0,0,0),0));owned.AddRange(copy.CreatedIds);
                    if(copy.Status!="committed"||copy.RequiresHostReview)throw new InvalidOperationException("Copy stage: "+copy.Status);
                    var copied=copy.CreatedIds;var extra=Selected(copied,()=>Geo.HostGeometry.Execute(Geo.HostGeometry.Prepare(copied,request)));owned.AddRange(extra);
                    if(source!=Encode(ids.Select(PorscheBindings.Shape)))throw new InvalidOperationException("Source changed during copy/edit.");
                }catch(Exception error){try{PorscheBindings.DeleteGeometry(owned);owned.Clear();}catch(Exception cleanup){throw new AggregateException(error,cleanup);}throw;}
            };
            b.Rollback=()=>{PorscheBindings.DeleteGeometry(owned);if(source!=Encode(ids.Select(PorscheBindings.Shape)))throw new InvalidOperationException("Original source changed.");};
            b.Readback=()=>new{created_ids=owned,source_preserved=source==Encode(ids.Select(PorscheBindings.Shape)),geometry=owned.Select(id=>new{id,exists=Geometry.RetrieveEntity(id)!=null,shape=Geometry.RetrieveEntity(id)==null?null:PorscheBindings.Shape(id)})};break;
        }
        case "xplus.holder_library": {
            var plan=HolderTools2027.Data.Validate(Read<HolderTools2027.HolderPlan>(c));HolderTools2027.WriteReceipt receipt=null;
            var path=Path.Combine(directory,"holders.tooldb");
            b.Preview=new{action,plan,profile=HolderTools2027.Data.SideEdges(plan),output_policy="new library in request artifacts; existing libraries untouched"};
            b.Apply=()=>{if(File.Exists(path))throw new IOException("Refuse existing output library.");receipt=HolderTools2027.Library.Create(plan,path,directory);if(receipt.Status!="Applied")throw new InvalidOperationException(receipt.Error??receipt.Status);};
            b.Rollback=()=>HolderTools2027.Library.Rollback(receipt);
            b.Readback=()=>new{receipt,holders=receipt==null?null:HolderTools2027.Library.ReadHolders(path),library_file_retained=true};break;
        }
        case "xplus.select_operation_chains": {
            int[] opids=Ids(q,"operation_ids"),before=GeometrySelection.Selected();
            var chains=opids.Select(id=>Op(id) as ChainBasedOperation??throw new ArgumentException("Chain-based operation required.")).SelectMany(o=>o.GetChainArray()).ToArray();
            // Enumerating the full chain array for selection does not submit a filtered native list.
            var info=chains.Select(ch=>new{ch.FirstEntityId,ch.IsClosed,ch.Perimeter,entity_ids=ChainManager.GetGeometryInChain(ch).Select(g=>g.GetEntityID()).ToArray()}).ToArray();
            var wanted=before.Concat(info.SelectMany(x=>x.entity_ids)).Distinct().Order().ToArray();
            b.Preview=new{action,operation_ids=opids,chains=info,selected_before=before,selected_after=wanted};
            b.Apply=()=>GeometrySelection.Set(wanted);b.Rollback=()=>{if(!GeometrySelection.Selected().SequenceEqual(wanted))throw new InvalidOperationException("Selection changed after apply.");GeometrySelection.Set(before);};
            b.Readback=()=>new{selected_ids=GeometrySelection.Selected()};break;
        }
        case "xplus.work_offset": {
            int id=I(q,"plane_id"),number=I(c,"number");
            MCView Plane()=>SearchManager.GetViews().Single(v=>v.ViewID==id);
            var original=Plane();short before=original.WorkOffsetNumber;
            var affected=SearchManager.GetOperations().Where(o=>o.ToolPlane.ViewID==id||o.WCS.ViewID==id||o.ConstructionPlane.ViewID==id).Select(o=>o.GetOperationID()).ToArray();
            b.Preview=new{action,plane_id=id,original.ViewName,work_offset_before=before,work_offset_after=number,affected_operation_ids=affected};
            void Set(short value){var plane=Plane();plane.WorkOffsetNumber=value;if(!plane.Commit()||Plane().WorkOffsetNumber!=value)throw new InvalidOperationException("Work offset readback mismatch.");}
            b.Apply=()=>{try{Set(checked((short)number));}catch{Set(before);throw;}};
            b.Rollback=()=>{if(Plane().WorkOffsetNumber!=number)throw new InvalidOperationException("Work offset changed after apply.");Set(before);};
            b.Readback=()=>new{plane_id=id,work_offset=Plane().WorkOffsetNumber};break;
        }
        case "xplus.rename_nci": {
            var items=c.GetProperty("names").EnumerateArray().Select(x=>new{id=I(x,"operation_id"),name=S(x,"name")}).ToArray();
            foreach(var x in items)if(Op(x.id).Locked)throw new ArgumentException("Operation locked.");
            var changes=items.Select(x=>new{x.id,original=Op(x.id).NCIName,target=Path.Combine(Path.GetDirectoryName(Op(x.id).NCIName)??"",x.name+Path.GetExtension(Op(x.id).NCIName))}).ToArray();
            b.Preview=new{action,changes,policy="preserve NCI directories; no posting or file renaming"};
            void Set(int id,string path){OpSelection(new[]{id});if(OperationsManager.SetProgramName(path,false)!=1||!string.Equals(Op(id).NCIName,path,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("NCI name readback mismatch.");}
            void RestoreSelection(int[] selection){OpSelection(selection);}
            b.Apply=()=>{var selection=SearchManager.GetOperationIDs(false);var attempted=new List<int>();try{foreach(var x in changes){attempted.Add(x.id);Set(x.id,x.target);}}catch(Exception cause){var failures=new List<Exception>{cause};foreach(var id in attempted.AsEnumerable().Reverse())try{Set(id,changes.Single(x=>x.id==id).original);}catch(Exception e){failures.Add(e);}throw new AggregateException("NCI change failed; see restoration results.",failures);}finally{RestoreSelection(selection);}};
            b.Rollback=()=>{foreach(var x in changes)if(!string.Equals(Op(x.id).NCIName,x.target,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("NCI name changed after apply.");var selection=SearchManager.GetOperationIDs(false);try{foreach(var x in changes)Set(x.id,x.original);}finally{RestoreSelection(selection);}};
            b.Readback=()=>new{names=changes.Select(x=>new{x.id,nci=Op(x.id).NCIName})};break;
        }
        default:throw new ArgumentException("Unsupported typed utility: "+action);
        }
        return b;
    }
}
