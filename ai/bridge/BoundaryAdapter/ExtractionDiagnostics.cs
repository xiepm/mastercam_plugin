using System;
using System.Collections.Generic;
using System.Linq;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Support;

namespace MastercamPluginAI.BoundaryAdapter;

public sealed record ReturnedGeometry(int Index,bool IsNull,string ActualType,int? Id,bool? Selected,bool? Blanked,int? Level,V3[] LineEndpoints,string InspectionError);
public sealed record ExtractionReport(bool ArrayIsNull,int? Count,string Classification,ReturnedGeometry[] Items,int[] SelectionBefore,int[] SelectionAfter,
    int[] InventoryBefore,int[] InventoryAfter,int[] AddedIds,int[] RemovedIds);

/// <summary>Diagnostic DTOs only: no reinterpretation, conversion, widening, or curve fitting.</summary>
public static class ExtractionDiagnostics
{
    internal static int[] SelectedIds()=>SearchManager.GetSelectedGeometry().Select(g=>g.GetEntityID()).Order().ToArray();
    internal static ReturnedGeometry Describe(Geometry g,int index)
    {
        if(g==null)return new(index,true,null,null,null,null,null,null,null);
        string type=g.GetType().FullName;int? id=null,level=null;bool? selected=null,blanked=null;V3[] points=null;var errors=new List<string>();
        try{id=g.GetEntityID();}catch(Exception e){errors.Add("ID: "+e.Message);}
        try{selected=g.Selected;blanked=g.Blanked;level=g.Level;}catch(Exception e){errors.Add("Attributes: "+e.Message);}
        if(g is LineGeometry line)try{points=new[]{NativeBoundary.V(line.EndPoint1),NativeBoundary.V(line.EndPoint2)};}catch(Exception e){errors.Add("Endpoints: "+e.Message);}
        return new(index,false,type,id,selected,blanked,level,points,errors.Count==0?null:string.Join(" | ",errors));
    }
    internal static ExtractionReport Report(Geometry[] returned,int[] beforeSelection,IEnumerable<int> beforeIds)
    {
        int[] before=beforeIds.Order().ToArray(),after=NativeBoundary.Inventory().Select(g=>g.GetEntityID()).Order().ToArray();
        var items=returned?.Select(Describe).ToArray()??Array.Empty<ReturnedGeometry>();
        string classification=returned==null?"NULL_ARRAY":returned.Length==0?"EMPTY_ARRAY":returned.Any(g=>g==null)?"NULL_ELEMENT":
            returned.Any(g=>g is not LineGeometry)?"NON_LINE_ELEMENT":"ALL_LINE_ELEMENTS";
        return new(returned==null,returned?.Length,classification,items,beforeSelection,SelectedIds(),before,after,after.Except(before).ToArray(),before.Except(after).ToArray());
    }
    internal static object SelectionState()=>new{
        selectedIds=SelectedIds(),geometry=NativeBoundary.Inventory().Select(Describe).ToArray(),
        visibleLevels=LevelsManager.GetVisibleLevelNumbers(),mainLevel=SettingsManager.MainLevel,
        onlyActiveLevelVisible=LevelsManager.GetOnlyActiveLevelVisibleSetting(),allLevelsOff=LevelsManager.GetAllOff(),allLevelsOn=LevelsManager.GetAllOn()};
    internal static void RequireLines(ExtractionReport report)
    {
        BoundaryKernel.Require(!report.ArrayIsNull,"CreateEdgeCurves returned null; see extraction-return audit.");
        BoundaryKernel.Require(report.Count>0,"CreateEdgeCurves returned an empty array; see selection/display-list diagnostics.");
        BoundaryKernel.Require(!report.Items.Any(g=>g.IsNull),"CreateEdgeCurves returned null elements at: "+string.Join(",",report.Items.Where(g=>g.IsNull).Select(g=>g.Index)));
        BoundaryKernel.Require(report.Classification=="ALL_LINE_ELEMENTS","CreateEdgeCurves returned unsupported actual types: "+string.Join(",",report.Items.GroupBy(g=>g.ActualType).Select(g=>g.Key+"="+g.Count())));
        BoundaryKernel.Require(report.Items.All(g=>g.InspectionError==null),"CreateEdgeCurves return inspection failed; see per-item InspectionError.");
    }
}
