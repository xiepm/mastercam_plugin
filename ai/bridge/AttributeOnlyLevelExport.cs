using System;
using System.Linq;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Operations;
using LevelExport2027.Core;
using PorscheAdvanced2027;

namespace MastercamPluginAI;

// Reuse the shipping exporter/coordinator and binary-STL validator. Its old host
// selected solids through Geometry.Commit(), which regenerates parametric solids.
// This host changes only selection attributes through the verified Porsche adapter.
public sealed class AttributeOnlyLevelExport:ILevelExportHost
{
    public HostState ReadState()=>LevelExport2027.ExportService.CaptureState();
    static Operation[] Operations(int[] ids)=>ids.Select(id=>SearchManager.GetOperations(false).Single(o=>o.GetOperationID()==id)).ToArray();
    public void PreflightRestore(HostState state){foreach(var e in state.Entities)if(Geometry.RetrieveEntity(e.Id)==null)throw new InvalidOperationException("Missing geometry.");Operations(state.SelectedOperationIds);}
    public int[] SelectLevel(int level){var ids=GeometrySelection.All().Where(g=>g.Level==level&&!g.Blanked).Select(g=>g.GetEntityID()).Order().ToArray();GeometrySelection.Set(ids);return ids;}
    public bool WriteMesh(string path,double tolerance)=>FileManager.WriteSTL(path,-1,tolerance,false,true,false,false,false);
    public void Restore(HostState before){
        StateComparison.RequireSameDocument(before,ReadState());
        GeometrySelection.Set(before.Entities.Where(e=>e.Selected).Select(e=>e.Id).ToArray());
        if(!SearchManager.GetOperationIDs(false).Order().SequenceEqual(before.SelectedOperationIds.Order())){var ops=Operations(before.SelectedOperationIds);OperationsManager.UnSelectAllOperations();if(ops.Length>0)OperationsManager.SelectOperations(ops);}
        if(!StateComparison.Same(before,ReadState()))throw new InvalidOperationException("Export context changed beyond selection; refusing to hide the change.");
    }
}
