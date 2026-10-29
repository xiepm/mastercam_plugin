using System;
using System.Linq;
using Mastercam.IO;

namespace MastercamPluginAI.EdgeAdapter;

internal static class NativeLevelGroups
{
    // API29 XML: GetGroups enumerates the groups; GetLevelNumbersByGroupId enumerates
    // levels within each registered group. Empty is a documented result, not an exception.
    // The API exposes no separate status for an empty result. Two equal complete reads
    // detect instability, but cannot diagnose an unreported native-engine failure.
    internal static LevelGroupEvidence[] Capture()
    {
        LevelGroupEvidence[] Read()
        {
            var registry=LevelsManager.GetGroups();
            BoundaryKernel.Require(registry!=null&&registry.Count<=4096&&registry.All(g=>g!=null),"Missing/unsupported group registry.");
            var groups=registry.OrderBy(g=>g.Item1).Select(g=>
            {
                BoundaryKernel.Require(g.Item1>0&&g.Item2!=null&&LevelsManager.GetGroupName(g.Item1)==g.Item2,"Registered group identity/name readback mismatch.");
                var members=LevelsManager.GetLevelNumbersByGroupId(g.Item1);
                BoundaryKernel.Require(members!=null&&members.Count<=999999,"Missing/unsupported group member response.");
                return new LevelGroupEvidence(g.Item1,g.Item2,members.Order().ToArray());
            }).ToArray();
            LevelGroupContract.Validate(groups);return groups;
        }
        var first=Read();var second=Read();LevelGroupContract.RequireSame(first,second);return first;
    }
}
