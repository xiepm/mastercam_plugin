using System;
using System.Collections.Generic;
using Mastercam.Operations;
using Mastercam.Operations.Types;
using Mastercam.Support;
using TpSketcher2027;
namespace MastercamPluginAI;
// Preserve the existing chain/parameter checks; regenerate a freshly retrieved native operation.
public sealed class SketchHostAdapter : ISketchHost
{
    readonly MastercamHost host=new();
    public bool TransactionActive=>host.TransactionActive;
    public Inventory Inventory()=>host.Inventory();
    public SketchPlane Plane(int id)=>host.Plane(id);
    public EnvironmentState Environment()=>host.Environment();
    public void Restore(EnvironmentState s){PorscheAdvanced2027.GeometrySelection.Set(s.Selected);host.Restore(s);}
    public void Begin()=>host.Begin();public void Commit()=>host.Commit();public void Cancel()=>host.Cancel();
    public ObjectState Read(OwnedId id)=>host.Read(id);
    public int CreateLine(Segment s,int level,int color,Action<OwnedId> allocated)=>host.CreateLine(s,level,color,allocated);
    public int CreateTool(ToolDefinition d,Action<OwnedId> allocated)=>host.CreateTool(d,allocated);
    public void ValidateExistingTool(int slot,double diameter)=>host.ValidateExistingTool(slot,diameter);
    public bool Delete(OwnedId id)=>host.Delete(id);
    public bool HasForeignReferences(IReadOnlyCollection<OwnedId> ids)=>host.HasForeignReferences(ids);
    public int CreateContour(SketchPlan plan,MachiningSettings settings,int slot,IReadOnlyList<int[]> chains,Action<OwnedId> allocated)
    {
        using var selection=new PorscheAdvanced2027.GeometrySelection();PorscheAdvanced2027.GeometrySelection.Set(Array.Empty<int>());
        int id=host.CreateContour(plan,settings with{Regenerate=false},slot,chains,allocated);
        var fresh=SearchManager.GetOperation(id) as ContourOperation??throw new InvalidOperationException("Created contour missing");
        fresh.ContourSubtype=ContourSubtypeType.Basic;fresh.CutParams.ContourSubtype=ContourSubtypeType.Basic;
        fresh.Posting=false;fresh.MarkDirty();if(!fresh.Commit(false))throw new InvalidOperationException("Fresh contour posting commit failed");
        var actual=SearchManager.GetOperation(id) as ContourOperation;
        if(actual==null||actual.Posting||actual.CutParams.ContourSubtype!=ContourSubtypeType.Basic)throw new InvalidOperationException("Canonical contour subtype/posting readback failed");
        return id;
    }
}
