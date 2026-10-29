using System;
using System.Collections.Generic;
using System.Linq;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.IO.Types;
using Mastercam.Math;
using Mastercam.Support;
using Mastercam.Support.Types;
using Mastercam.Database.Types;
namespace MastercamPluginAI.EdgeAdapter;
public static partial class NativeBoundary
{
    internal static FaceEvidence[] ReadFaces(int sourceId)
    {
        var before=Capture();
        BoundaryKernel.Require(Inventory().Any(g=>g.GetEntityID()==sourceId&&g is SolidGeometry),"Source is not an alive solid body.");
        Dictionary<int,int> map=null;int[] selectionBefore=ExtractionDiagnostics.SelectedIds();
        try
        {
            // API29 IL 0x06002411 clears selected bit 4 with add_undo=false before returning faces.
            // This query is NOT read-only with respect to selection. Preserve it explicitly, even on error.
            map=SearchManager.GetFaceTagsAndPidMapFromBodyEntity(sourceId);
            Record("face-map-query-selection",new{sourceId,before=selectionBefore,afterRawCall=ExtractionDiagnostics.SelectedIds(),faceCount=map?.Count});
        }
        finally
        {
            RestoreSelection(before);VerifyIds(before.Keys);VerifyExisting(before);
            Record("face-map-selection-restored",new{sourceId,selected=ExtractionDiagnostics.SelectedIds()},verified:true);
        }
        BoundaryKernel.Require(map is {Count:>=1 and <=1024}&&map.Values.Distinct().Count()==map.Count,"Invalid/incomplete face map.");
        foreach(int tag in map.Values)
        {
            var result=SearchManager.GetFaceTypeAndParameters(tag);
            BoundaryKernel.Require(result?.ResultType is ResultType kind&&kind==ResultType.Plane,"Only true planar faces are supported; curved/unknown faces rejected.");
        }
        BoundaryKernel.Require(map.Count>=4,"Too few planar faces for a closed volume.");
        return map.OrderBy(k=>k.Key).Select(k=>
        {
            var tags=SearchManager.GetEdgeTagsFromFace(k.Value);
            BoundaryKernel.Require(tags is {Length:>=3},"Face edge lookup failed.");
            return new FaceEvidence(k.Key,V(SearchManager.GetFaceNormal(k.Value)),tags.Order().ToArray());
        }).ToArray();
    }
    static T RolledBack<T>(Dictionary<int,Stamp> baseline,Func<T> work,Func<IEnumerable<int>> observedReturnedIds=null)
    {
        string context=ContextSeal();
        BoundaryKernel.Require(UndoManager.StartTransaction(),"Extraction transaction could not start.");
        T value=default;Exception original=null;
        try{value=work();}catch(Exception e){original=e;}
        try{CancelAndVerify(baseline,context,observedReturnedIds?.Invoke());}catch(Exception e){throw new AggregateException("Extraction rollback was not verified.",original==null?new[]{e}:new[]{original,e});}
        if(original!=null)System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(original).Throw();
        return value;
    }
    internal static void RequireWorldXY(MCView view)
    {
        BoundaryKernel.Require(view!=null,"Missing chain/CPlane view.");var m=view.ViewMatrix;
        BoundaryKernel.Require((V(m.Row1)-new V3(1,0,0)).Length<1e-10&&(V(m.Row2)-new V3(0,1,0)).Length<1e-10&&
            (V(m.Row3)-new V3(0,0,1)).Length<1e-10,"Native v1 requires a World-XY oriented CPlane/chain view; no plane is changed.");
    }

}
