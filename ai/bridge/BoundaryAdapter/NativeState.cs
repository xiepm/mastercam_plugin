using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Math;
using Mastercam.Support;
using Mastercam.Support.Types;
using Mastercam.Database.Types;

namespace MastercamPluginAI.BoundaryAdapter;

public sealed record AuditStep(string Name,int[] GeometryIds,bool? Verified,string Detail);
public static partial class NativeBoundary
{
    static readonly List<AuditStep> audit=new();
    public static AuditStep[] LastAudit=>audit.ToArray();
    internal static void ClearAudit()=>audit.Clear();
    internal static void Record(string name,object detail,int[] ids=null,bool? verified=null)=>audit.Add(new(name,ids??Array.Empty<int>(),verified,JsonSerializer.Serialize(detail)));
    internal sealed record Stamp(string Type,DateTime Time,int Level,int Color,bool Selected,bool Blanked,string Shape);
    internal static Geometry[] Inventory()
    {
        // GetSolidBodyEntities is deliberately excluded: API29 clears selected bits with add_undo=false.
        // All Alive does not substitute for an explicit blanked query.
        var alive=SearchManager.GetGeometry(new SelectionMask(true,false,false));
        var blanked=SearchManager.GetGeometry(new SelectionMask(false,false,true));
        var selected=SearchManager.GetSelectedGeometry();
        BoundaryKernel.Require(alive!=null&&blanked!=null&&selected!=null,"Inventory query returned null.");
        var all=alive.Concat(blanked).Concat(selected).GroupBy(g=>g.GetEntityID()).Select(g=>g.First()).ToArray();
        BoundaryKernel.Require(all.All(g=>g.GetEntityID()>0),"Invalid inventory identity.");
        var solids=SearchManager.GetSolidGeometry(new SelectionMask(true,false,false)).Concat(SearchManager.GetSolidGeometry(new SelectionMask(false,false,true)));
        BoundaryKernel.Require(solids.All(g=>all.Any(x=>x.GetEntityID()==g.GetEntityID())),"Inventory omitted a solid found by non-mutating geometry masks.");
        return all;
    }
    internal static Dictionary<int,Stamp> Capture()=>Inventory().ToDictionary(g=>g.GetEntityID(),StampOf);
    internal static string ContextSeal()
    {
        object View(MCView v)=>new{v.ViewNumber,v.ViewID,origin=V(v.ViewOrigin),rows=new[]{V(v.ViewMatrix.Row1),V(v.ViewMatrix.Row2),V(v.ViewMatrix.Row3)}};
        var groups=NativeLevelGroups.Capture();
        return JsonSerializer.Serialize(new{file=FileManager.CurrentFileName,cplane=View(ViewManager.CPlane),tplane=View(ViewManager.TPlane),
            wcs=View(ViewManager.WorkCoordinateSystem),gview=View(ViewManager.GraphicsView),depth=ViewManager.ConstructionDepth,
            mainLevel=SettingsManager.MainLevel,chainTolerance=ChainManager.ChainTolerance,systemTolerance=SettingsManager.SystemTolerance,
            visibleLevels=LevelsManager.GetVisibleLevelNumbers().Order().ToArray(),onlyActiveLevelVisible=LevelsManager.GetOnlyActiveLevelVisibleSetting(),
            allLevelsOff=LevelsManager.GetAllOff(),allLevelsOn=LevelsManager.GetAllOn(),
            activeLevels=LevelsManager.GetActiveLevelNumbers().Order().ToArray(),mainLevelAlwaysVisible=LevelsManager.GetMainLevelVisibleSetting(),
            namedLevels=LevelsManager.GetLevelNumbersWithNames().Order().Select(n=>new{number=n,name=LevelsManager.GetLevelName(n)}).ToArray(),
            levelGroups=groups.Select(g=>new{id=g.Id,name=g.Name}).ToArray(),levelGroupMembers=groups});
    }
    internal static void VerifyContext(string expected)
    {
        string actual=ContextSeal();
        var differences=ContextContract.Differences(expected,actual);
        if(differences.Length>0){Record("host-context-mismatch",new{expected,actual,differences},verified:false);throw new InvalidOperationException("Host context changed: "+string.Join(",",differences.Select(d=>d.Field)));}
    }
    static Stamp StampOf(Geometry g)=>new(g.GetType().FullName,g.TimeStamp,g.Level,g.Color,g.Selected,g.Blanked,
        g is LineGeometry l?JsonSerializer.Serialize(new[]{V(l.EndPoint1),V(l.EndPoint2)}):"");
    internal static void VerifyExisting(Dictionary<int,Stamp> baseline)
    {
        var now=Capture();
        foreach(var pair in baseline)
        {
            bool exists=now.TryGetValue(pair.Key,out var actual);
            if(!exists||actual!=pair.Value)
            {
                Record("existing-state-mismatch",new{id=pair.Key,expected=pair.Value,exists,actual},new[]{pair.Key},false);
                throw new InvalidOperationException("Existing geometry/selection changed: "+pair.Key+"; see existing-state-mismatch.");
            }
        }
    }
    internal static void VerifyIds(IEnumerable<int> expected)
    {
        int[] wanted=expected.Order().ToArray(),actual=Inventory().Select(g=>g.GetEntityID()).Order().ToArray();
        if(!actual.SequenceEqual(wanted))
        {
            Record("inventory-mismatch",new{expected=wanted,actual,added=actual.Except(wanted).ToArray(),missing=wanted.Except(actual).ToArray()},verified:false);
            throw new InvalidOperationException("Geometry inventory mismatch (alive + blanked + selected union); see inventory-mismatch.");
        }
    }
    internal static void RequireAbsent(int id)
    {
        Geometry g=null;
        try{g=Geometry.RetrieveEntity(id);}
        catch(Mastercam.App.Exceptions.IDNotFoundException){return;}
        catch(Mastercam.App.Exceptions.EntityInvalidException){return;}
        BoundaryKernel.Require(g==null||g.GetEntityID()!=id,"Deleted temporary geometry ID remains retrievable: "+id);
    }
    internal static void RestoreSelection(Dictionary<int,Stamp> baseline)
    {
        var changed=new List<int>();
        foreach(var g in Inventory())
        {
            bool want=baseline.TryGetValue(g.GetEntityID(),out var stamp)&&stamp.Selected;
            if(g.Selected!=want){changed.Add(g.GetEntityID());PorscheAdvanced2027.GeometrySelection.Set(baseline.Where(p=>p.Value.Selected).Select(p=>p.Key).ToArray());}
        }
        var selected=SearchManager.GetSelectedGeometry().Select(g=>g.GetEntityID()).Order();
        BoundaryKernel.Require(selected.SequenceEqual(baseline.Where(p=>p.Value.Selected).Select(p=>p.Key).Order()),"Selection readback mismatch.");
        if(changed.Count>0)Record("selection-restoration-readback",new{changedIds=changed.ToArray(),selectedIds=selected.ToArray()},changed.ToArray(),true);
    }
    internal static void CancelAndVerify(Dictionary<int,Stamp> baseline,string contextSeal=null,IEnumerable<int> observedReturnedIds=null,NativeOutputLevelLease outputLevel=null,Action verifyDocument=null)
    {
        int[] temporary=Array.Empty<int>();Dictionary<int,Stamp> journal=null;Exception inventoryError=null;
        try{journal=Capture().Where(p=>!baseline.ContainsKey(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);temporary=journal.Keys.ToArray();}catch(Exception e){inventoryError=e;}
        audit.Add(new("cancel-request",temporary,null,"CancelTransaction is a request, not restoration evidence."));
        BoundaryKernel.Require(UndoManager.IsTransactionActive(),"Owned transaction disappeared; refusing blind Undo.");
        UndoManager.CancelTransaction();
        BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"Cancellation did not end transaction.");
        var residue=Inventory().Where(g=>!baseline.ContainsKey(g.GetEntityID())).ToArray();
        Record("cancel-direct-readback",new{observedTemporaryIds=temporary,returnedIds=observedReturnedIds?.ToArray(),residualIds=residue.Select(g=>g.GetEntityID()).ToArray(),transactionActive=UndoManager.IsTransactionActive()});
        if(residue.Length>0)
        {
            // Some creation APIs may not enlist geometry in Undo. Never infer that Cancel deleted it.
            // Delete only exact journaled new lines; source or unrecognized residue stops cleanup.
            VerifyExisting(baseline);
            BoundaryKernel.Require(journal!=null&&residue.All(g=>g is LineGeometry&&journal.TryGetValue(g.GetEntityID(),out var stamp)&&StampOf(g)==stamp),
                "Unrecognized/changed rollback residue; refusing to delete it.");
            BoundaryKernel.Require(UndoManager.StartTransaction(),"Could not start exact residue cleanup.");
            try
            {
                foreach(var g in residue)BoundaryKernel.Require(g.Delete(false),"Could not delete exact owned residue: "+g.GetEntityID());
                UndoManager.CommitTransaction();
                BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"Residue cleanup transaction remained active.");
            }
            catch{if(UndoManager.IsTransactionActive())UndoManager.CancelTransaction();throw;}
            audit.Add(new("journaled-line-residue-deleted",residue.Select(g=>g.GetEntityID()).ToArray(),true,"Cancel left geometry. Deleted only new lines whose full journal stamp and endpoints matched; original inventory was intact."));
        }
        RestoreSelection(baseline);VerifyIds(baseline.Keys);VerifyExisting(baseline);
        foreach(int id in temporary.Concat(observedReturnedIds??Array.Empty<int>()).Distinct())RequireAbsent(id);
        verifyDocument?.Invoke();
        if(outputLevel!=null)
        {
            outputLevel.RestoreAfterRollback();
            // Layer cleanup is the final mutator: recheck geometry and selection after it too.
            VerifyIds(baseline.Keys);VerifyExisting(baseline);
            foreach(int id in temporary.Concat(observedReturnedIds??Array.Empty<int>()).Distinct())RequireAbsent(id);
            verifyDocument?.Invoke();
        }
        if(contextSeal!=null)VerifyContext(contextSeal);
        if(inventoryError!=null)throw new InvalidOperationException("Cancellation completed and baseline was checked, but pre-cancel temporary inventory was unavailable.",inventoryError);
        audit.Add(new("cancel-restoration-verified",temporary.Concat(observedReturnedIds??Array.Empty<int>()).Distinct().ToArray(),true,"All/blanked inventory, direct ID absence, timestamps, selected flags and line coordinates read back."));
    }
    internal static V3 V(Point3D p)=>new(p.x,p.y,p.z);
    internal static Point3D P(V3 p)=>new(p.X,p.Y,p.Z);
}
