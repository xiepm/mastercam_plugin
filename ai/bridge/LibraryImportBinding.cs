using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text.Json;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Support.Types;
using Mastercam.Operations;
using PorscheAdvanced2027;
namespace MastercamPluginAI;
internal static class LibraryImportBinding
{
    internal static PorscheBinding Prepare(JsonElement q,string directory)
    {
        var c=q.GetProperty("parameters");string path=c.GetProperty("path").GetString(),hash=c.GetProperty("sha256").GetString();int target=c.GetProperty("target_group_id").GetInt32();int[] wanted=c.GetProperty("library_operation_ids").EnumerateArray().Select(x=>x.GetInt32()).ToArray();
        if(c.GetProperty("include_geometry").GetBoolean())throw new ArgumentException("Geometry import is unavailable: API29 native regression failed. Use a parameter-only library import.");
        string Sha()=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
        if(!Path.IsPathFullyQualified(path)||!path.EndsWith(".mcam-operations",StringComparison.OrdinalIgnoreCase)||!File.Exists(path)||new FileInfo(path).Length>512L*1024*1024||!string.Equals(Sha(),hash,StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Library path/size/hash mismatch.");
        if(GroupManager.GetActiveGroup()?.ID!=target||GroupManager.FindGroupByID(target)?.IsToolpathGroup()!=true)throw new ArgumentException("Target must be the current active toolpath group.");
        ExternalGroupsFileData[] groups=Array.Empty<ExternalGroupsFileData>();ExternalOpsFileData[] items=Array.Empty<ExternalOpsFileData>();if(!SearchManager.GetOpGroupDataInExternalFile(path,ref groups,ref items)||wanted.Any(id=>items.Count(o=>o.OpIdn==id)!=1)||wanted.Length!=wanted.Distinct().Count())throw new ArgumentException("Library operation IDs mismatch.");
        var originalOps=SearchManager.GetOperationIDs(true);var originalGeometry=GeometrySelection.All().Select(g=>g.GetEntityID()).ToArray();var originalTools=SearchManager.GetTools().Select(t=>(int)t.Slot).ToArray();var originalViews=SearchManager.GetViews().Select(v=>(int)v.ViewID).ToArray();var originalGroups=WorkshopBindings.Groups().Select(g=>g.ID).ToArray();var selection=SearchManager.GetOperationIDs(false);string before=LibraryState.Capture(),after=null;
        var ops=new List<int>();var geometry=new List<int>();var tools=new List<int>();var planes=new List<int>();string status="Prepared",error=null;
        void Capture(){geometry=GeometrySelection.All().Select(g=>g.GetEntityID()).Except(originalGeometry).ToList();tools=SearchManager.GetTools().Select(t=>(int)t.Slot).Except(originalTools).ToList();planes=SearchManager.GetViews().Select(v=>(int)v.ViewID).Except(originalViews).ToList();}
        void RestoreSelection(){OperationsManager.UnSelectAllOperations();if(selection.Length>0)OperationsManager.SelectOperations(selection.Select(SearchManager.GetOperation).ToArray());OperationsManager.InitOperationsManagerTree();}
        object Current()=>new{status,error,created_operation_ids=ops,created_geometry_ids=geometry,created_tool_slots=tools,created_plane_ids=planes,operations=ops.Select(id=>new{id,exists=SearchManager.GetOperationData(id)?.IsValid==true,type=SearchManager.GetOperationData(id)?.IsValid==true?SearchManager.GetOperation(id)?.GetType().Name:null}),source_path=path,source_sha256=hash};
        void Save(){Directory.CreateDirectory(directory);File.WriteAllText(Path.Combine(directory,"library-import.json"),WorkshopBindings.Encode(Current()));}
        void Cleanup(){foreach(int id in ops.AsEnumerable().Reverse()){var op=SearchManager.GetOperation(id);if(op!=null&&(originalOps.Contains(id)||!op.Delete()))throw new InvalidOperationException("Import operation cleanup failed.");}foreach(int id in geometry.AsEnumerable().Reverse()){var g=Geometry.RetrieveEntity(id);if(g!=null&&(originalGeometry.Contains(id)||!g.Delete()))throw new InvalidOperationException("Import geometry cleanup failed.");}foreach(int slot in tools.AsEnumerable().Reverse()){var t=SearchManager.GetTools().SingleOrDefault(x=>x.Slot==slot);if(t!=null&&(SearchManager.GetOperations().Any(o=>o.OperationTool?.Slot==slot)||!t.Delete()))throw new InvalidOperationException("Imported tool in use/cleanup failed.");}foreach(int id in planes.AsEnumerable().Reverse()){var p=SearchManager.GetViews().SingleOrDefault(v=>v.ViewID==id);if(p!=null&&(p.IsInUseView||p.IsLockedView||!p.Delete()))throw new InvalidOperationException("Imported view in use/cleanup failed.");}RestoreSelection();LibraryState.RequireEqual(before,LibraryState.Capture(),directory,"import-cleanup");}
        var b=new PorscheBinding{Preview=new{action="operations.import",path,sha256=hash,target_group_id=target,operation_ids=wanted,include_geometry=c.GetProperty("include_geometry").GetBoolean(),set_views_to_current=c.GetProperty("set_views_to_current").GetBoolean(),library=RemainingBindings.LibraryInfo(path),regenerates=false,posting=false,scope="Parameters and tools only; imported operation requires explicit geometry assignment before regeneration",tool_policy="Native duplicate-tool check enabled; owned new tools recorded"}};
        b.Apply=()=>{
            try{
                if(Sha()!=hash.ToUpperInvariant()||GroupManager.GetActiveGroup()?.ID!=target)throw new InvalidOperationException("Library/target changed before import.");
                foreach(int id in wanted){
                    var prior=SearchManager.GetOperationIDs(true);Operation op=null;
                    try{status="Importing";Save();op=OperationsManager.ImportOperation(new OperationsManager.ImportOptions{FilePath=path,OperationID=id,CalcFeedsAndSpeed=false,ImportOperationGeometry=c.GetProperty("include_geometry").GetBoolean(),ImportOperationGroups=false,SetOpViewsToCurrentSystemViews=c.GetProperty("set_views_to_current").GetBoolean(),DisableDuplicateToolCheck=false});}
                    finally{ops.AddRange(SearchManager.GetOperationIDs(true).Except(prior));status="NativeReturned";Save();Capture();Save();}
                    if(op==null||originalOps.Contains(op.GetOperationID())||!ops.Contains(op.GetOperationID()))throw new InvalidOperationException("Import did not return an owned operation.");op.GroupNumber=target;op.Posting=false;op.MarkDirty();if(!op.Commit(false))throw new InvalidOperationException("Imported operation parameter commit failed.");var fresh=SearchManager.GetOperation(op.GetOperationID());if(fresh==null||fresh.GroupNumber!=target||fresh.Posting||!fresh.Dirty)throw new InvalidOperationException("Imported operation fresh readback mismatch.");
                }
                if(ops.Count!=wanted.Length||!WorkshopBindings.Groups().Select(g=>g.ID).Order().SequenceEqual(originalGroups.Order()))throw new InvalidOperationException("Unexpected imported operation/group count.");
                RestoreSelection();after=LibraryState.Capture();status="Applied";Save();
            }catch(Exception e){error=e.ToString();Capture();try{Cleanup();status="RestoredAfterFailure";}catch(Exception cleanup){status="RestoreIncomplete";error+="\n"+cleanup;}Save();throw new InvalidOperationException(status+": "+error,e);}finally{RestoreSelection();}
        };
        b.Rollback=()=>{LibraryState.RequireEqual(after,LibraryState.Capture(),directory,"import-rollback-preflight");Cleanup();status="RolledBack";Save();};b.Readback=Current;return b;
    }
}
