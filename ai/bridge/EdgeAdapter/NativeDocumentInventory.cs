using System;
using System.Linq;
using System.Text.Json;
using Mastercam.Database;
using Mastercam.Support;

namespace MastercamPluginAI.EdgeAdapter;

/// <summary>Read-only operation/tool inventories for a level probe in a nonempty disposable file.
/// This is identity/common-attribute readback, not a bytewise serialization of all machining parameters.</summary>
internal static class NativeDocumentInventory
{
    internal sealed record Snapshot(int[] OperationIds,string[] Operations,string[] Tools);
    static string ToolStamp(Tool t)=>t==null?null:JsonSerializer.Serialize(new{
        type=t.GetType().FullName,t.Slot,t.Number,t.ToolTypeID,t.Name,t.Diameter,t.Length,t.CornerRadius,
        t.LengthOffset,t.DiameterOffset,t.Flutes,t.FluteLength,t.ShoulderLength,t.Feed,t.PlungeFeed,t.RetractFeed,t.RPM,t.IsMetric});
    internal static Snapshot Capture()
    {
        var operations=SearchManager.GetOperations();var tools=SearchManager.GetTools();
        BoundaryKernel.Require(operations!=null&&tools!=null&&operations.All(o=>o!=null)&&tools.All(t=>t!=null),"Operation/tool inventory unavailable.");
        var ordered=operations.OrderBy(o=>o.GetOperationID()).ToArray();var ids=ordered.Select(o=>o.GetOperationID()).ToArray();
        BoundaryKernel.Require(ids.All(n=>n>0)&&ids.Distinct().Count()==ids.Length,"Invalid operation identities.");
        return new(ids,ordered.Select(o=>JsonSerializer.Serialize(new{
            id=o.GetOperationID(),type=o.GetType().FullName,o.Name,o.Type,o.GroupNumber,o.TimeStamp,o.Selected,o.Dirty,o.Locked,
            o.Posting,o.ProgramNumber,o.NCIName,o.DisplayToolpath,o.ToolDisplayOn,o.ToBatch,o.ForceToolChangeOn,
            o.FeedRate,o.PlungeRate,o.RetractRate,o.SpindleSpeed,o.DiameterOffset,o.LengthOffset,tool=ToolStamp(o.OperationTool)
        })).ToArray(),tools.Select(ToolStamp).Order(StringComparer.Ordinal).ToArray());
    }
    internal static void Verify(Snapshot expected,string stage)
    {
        var actual=Capture();bool matches=JsonSerializer.Serialize(expected)==JsonSerializer.Serialize(actual);
        NativeBoundary.Record("operation-tool-inventory-readback",new{stage,operationCount=actual.Operations.Length,toolCount=actual.Tools.Length,expected,actual},verified:matches);
        BoundaryKernel.Require(matches,"Original operation/tool identities or common attributes changed; refusing to report restoration.");
    }
}
