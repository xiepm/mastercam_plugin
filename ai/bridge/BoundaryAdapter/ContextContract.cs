using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MastercamPluginAI.BoundaryAdapter;

public sealed record ContextChange(string Field,string ExpectedJson,string ActualJson);
public sealed record OutputLevelRepair(bool DeleteNewEmptyLevel,bool RestoreExistingVisibility,bool ExpectedVisibility);

/// <summary>Exact planned level artifact changes. Every unrelated context field remains mandatory.</summary>
public static class ContextContract
{
    public static ContextChange[] Differences(string expected,string actual)
    {
        using var a=JsonDocument.Parse(expected);using var b=JsonDocument.Parse(actual);
        return a.RootElement.EnumerateObject().Select(p=>p.Name).Union(b.RootElement.EnumerateObject().Select(p=>p.Name)).Order().Select(name=>
        {
            bool x=a.RootElement.TryGetProperty(name,out var av),y=b.RootElement.TryGetProperty(name,out var bv);
            return x&&y&&JsonElement.DeepEquals(av,bv)?null:new ContextChange(name,x?av.GetRawText():null,y?bv.GetRawText():null);
        }).Where(d=>d!=null).ToArray();
    }
    public static int[] Levels(string context,string name)
    {
        using var doc=JsonDocument.Parse(context);var levels=doc.RootElement.GetProperty(name).EnumerateArray().Select(v=>v.GetInt32()).ToArray();
        BoundaryKernel.Require(levels.All(n=>n>0)&&levels.Distinct().Count()==levels.Length&&levels.SequenceEqual(levels.Order()),"Invalid/unsorted level snapshot: "+name);return levels;
    }
    public static OutputLevelRepair PlanRollback(string before,string current,int target)
    {
        BoundaryKernel.Require(target>0,"Invalid output level identity.");
        var changes=Differences(before,current);
        BoundaryKernel.Require(changes.All(d=>d.Field is "visibleLevels" or "activeLevels"),"Unowned context change; refusing automatic restoration: "+string.Join(",",changes.Select(d=>d.Field)));
        var ba=Levels(before,"activeLevels");var ca=Levels(current,"activeLevels");var bv=Levels(before,"visibleLevels");var cv=Levels(current,"visibleLevels");
        BoundaryKernel.Require(bv.All(ba.Contains)&&cv.All(ca.Contains),"Visible level missing from active-level inventory.");
        BoundaryKernel.Require(ba.All(ca.Contains)&&ca.Except(ba).All(n=>n==target),"Unexpected level creation/deletion; only the requested new output level can be owned.");
        BoundaryKernel.Require(bv.Where(n=>n!=target).SequenceEqual(cv.Where(n=>n!=target)),"Unrelated level visibility changed.");
        bool existed=ba.Contains(target),present=ca.Contains(target);
        return new(!existed&&present,existed&&bv.Contains(target)!=cv.Contains(target),bv.Contains(target));
    }
    public static string ExpectedCommitted(string before,int target)
    {
        var active=Levels(before,"activeLevels");
        if(active.Contains(target))return before; // Every existing level, including its visibility, is preserved.
        var node=JsonNode.Parse(before).AsObject();
        node["activeLevels"]=JsonSerializer.SerializeToNode(active.Append(target).Order().ToArray());
        node["visibleLevels"]=JsonSerializer.SerializeToNode(Levels(before,"visibleLevels").Append(target).Order().ToArray());
        return node.ToJsonString();
    }
}
