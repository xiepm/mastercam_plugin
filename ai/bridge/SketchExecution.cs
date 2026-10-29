using System;
using System.Linq;
using System.Collections.Generic;
using Mastercam.Support;
using Mastercam.Operations;
using TpSketcher2027;
namespace MastercamPluginAI;
public static class SketchExecution
{
    public sealed class Receipt
    {
        public ObjectState[] Objects{get;internal set;}
        public int? OperationId{get;internal set;}
        public bool? RegenerateRaw{get;internal set;}
        public bool? FreshDirty{get;internal set;}
        public bool RolledBack{get;internal set;}
        public Dictionary<int,string> CreatedPlanes{get;internal set;}=new();
    }
    static Dictionary<int,string> NewPlanes(int[] before)=>SearchManager.GetViews().Where(v=>!before.Contains((int)v.ViewID)).ToDictionary(v=>(int)v.ViewID,PorscheAdvanced2027.HoleHost.PlaneState);
    static void DeletePlanes(Dictionary<int,string> planes)
    {
        foreach(var pair in planes.Reverse()){
            var v=SearchManager.GetViews().SingleOrDefault(v=>v.ViewID==pair.Key);if(v==null)continue;
            if(PorscheAdvanced2027.HoleHost.PlaneState(v)!=pair.Value||v.IsInUseView)throw new InvalidOperationException("Created plane changed or remains in use: "+pair.Key);
            if(!v.Delete()||SearchManager.GetViews().Any(x=>x.ViewID==pair.Key))throw new InvalidOperationException("Created plane delete failed: "+pair.Key);
        }
    }
    public static Receipt Create(ISketchHost host,SketchPlan plan,CreateSettings settings)
    {
        var before=host.Inventory();var environment=host.Environment();
        var beforePlanes=SearchManager.GetViews().Select(v=>(int)v.ViewID).ToArray();CreationReceipt c;
        try{c=SketchWorkflow.Create(host,plan,settings with{Machining=settings.Machining is null?null:settings.Machining with{Regenerate=false}});}
        catch(Exception error){try{DeletePlanes(NewPlanes(beforePlanes));}catch(Exception cleanup){throw new AggregateException(error,cleanup);}throw;}
        var r=new Receipt{Objects=c.Objects.ToArray(),OperationId=c.OperationId};
        try{
            if(settings.Machining?.Regenerate==true){r.RegenerateRaw=SearchManager.GetOperation(c.OperationId.Value).Regenerate();var op=SearchManager.GetOperation(c.OperationId.Value);r.FreshDirty=op?.Dirty;
                if(r.RegenerateRaw!=true||op==null||op.Dirty)throw new InvalidOperationException("Post-commit sketch regenerate failed: raw="+r.RegenerateRaw+" freshDirty="+r.FreshDirty);}
            host.Restore(environment);r.Objects=c.Objects.Select(o=>host.Read(o.Object)??throw new InvalidOperationException("Created object missing")).ToArray();r.CreatedPlanes=NewPlanes(beforePlanes);return r;
        }catch(Exception error){var errors=new List<Exception>{error};foreach(var item in c.Objects.Reverse())try{if(host.Read(item.Object)!=null&&(!host.Delete(item.Object)||host.Read(item.Object)!=null))throw new InvalidOperationException("Cleanup failed: "+item.Object);}catch(Exception e){errors.Add(e);}
            try{host.Restore(environment);DeletePlanes(NewPlanes(beforePlanes));if(!before.Same(host.Inventory())||host.TransactionActive)throw new InvalidOperationException("Cleanup inventory differs");}catch(Exception e){errors.Add(e);}throw new AggregateException("Sketch regeneration failed; owned-object cleanup results included.",errors);}
    }
    public static void Rollback(ISketchHost host,Receipt r)
    {
        if(r.RolledBack)return;if(host.TransactionActive)throw new InvalidOperationException("Host transaction active");
        foreach(var item in r.Objects)if(host.Read(item.Object)!=item)throw new InvalidOperationException("Created object changed: "+item.Object);
        if(host.HasForeignReferences(r.Objects.Select(o=>o.Object).ToArray()))throw new InvalidOperationException("Created objects now referenced elsewhere");
        var environment=host.Environment();bool begun=false;
        try{host.Begin();begun=true;foreach(var item in r.Objects.Reverse())if(!host.Delete(item.Object)||host.Read(item.Object)!=null)throw new InvalidOperationException("Delete failed: "+item.Object);host.Restore(environment);DeletePlanes(r.CreatedPlanes);host.Commit();begun=false;r.RolledBack=true;}
        catch{if(begun&&host.TransactionActive)host.Cancel();host.Restore(environment);throw;}
    }
}
