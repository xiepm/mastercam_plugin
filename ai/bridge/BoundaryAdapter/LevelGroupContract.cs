using System;
using System.Linq;
using System.Text.Json;

namespace MastercamPluginAI.BoundaryAdapter;

public sealed record LevelGroupEvidence(int Id,string Name,int[] Levels);

/// <summary>Ownership is based on the enumerated registry and every group's members, never a scalar group guess.</summary>
public static class LevelGroupContract
{
    public static void Validate(LevelGroupEvidence[] groups)
    {
        BoundaryKernel.Require(groups!=null&&groups.All(g=>g!=null&&g.Id>0&&g.Name!=null&&g.Levels!=null),"Invalid group registry response.");
        BoundaryKernel.Require(groups.Select(g=>g.Id).SequenceEqual(groups.Select(g=>g.Id).Distinct().Order()),"Duplicate/unsorted group registry.");
        foreach(var group in groups)
            BoundaryKernel.Require(group.Levels.All(n=>n>0&&n<=999999)&&group.Levels.SequenceEqual(group.Levels.Distinct().Order()),"Invalid/duplicate/unsorted group members.");
    }
    public static void RequireSame(LevelGroupEvidence[] before,LevelGroupEvidence[] current)
    {
        Validate(before);Validate(current);
        BoundaryKernel.Require(JsonSerializer.Serialize(before)==JsonSerializer.Serialize(current),"Real group registry/name/members changed; refusing automatic level cleanup.");
    }
    public static void RequireOwned(int target,bool existed,string beforeName,string currentName,LevelGroupEvidence[] before,LevelGroupEvidence[] current)
    {
        BoundaryKernel.Require(target>0&&beforeName!=null&&currentName!=null&&beforeName==currentName,"Output level name changed or unavailable; refusing automatic level cleanup.");
        RequireSame(before,current);
        if(!existed)
            BoundaryKernel.Require(beforeName.Length==0&&!before.Any(g=>g.Levels.Contains(target))&&!current.Any(g=>g.Levels.Contains(target)),
                "New output level must be unnamed and absent from every registered group's members.");
    }
}
