using System;
using System.Linq;
using Mastercam.IO;

namespace MastercamPluginAI.BoundaryAdapter;

/// <summary>Own only the requested output level's creation/visibility side effects, never all levels.</summary>
internal sealed class NativeOutputLevelLease
{
    sealed record TargetMetadata(string Name,int? GroupId,string GroupName);
    readonly int target;readonly string before;readonly TargetMetadata metadata;readonly LevelGroupEvidence[] groups;readonly int beforeEntityCount;
    readonly bool existed;bool creationAttempted;
    internal NativeOutputLevelLease(int level,string expectedContext)
    {
        target=level;before=expectedContext;NativeBoundary.VerifyContext(before);
        existed=ContextContract.Levels(before,"activeLevels").Contains(target);
        metadata=ReadMetadata();groups=NativeLevelGroups.Capture();beforeEntityCount=LevelsManager.GetLevelEntityCount(target,true);
        LevelGroupContract.RequireOwned(target,existed,metadata.Name,metadata.Name,groups,groups);
        BoundaryKernel.Require(existed||beforeEntityCount==0,"Inactive output level unexpectedly contains geometry.");
        Observe("before-output-transaction");NativeBoundary.VerifyContext(before);
    }
    TargetMetadata ReadMetadata()
    {
        var group=LevelsManager.GetGroupFromLevel(target);
        return new(LevelsManager.GetLevelName(target),group?.Item1,group?.Item2);
    }
    internal void MarkCreationAttempt()=>creationAttempted=true;
    internal void Observe(string stage)
    {
        string current=NativeBoundary.ContextSeal();
        NativeBoundary.Record("output-level-stage",new{stage,target,existedBefore=existed,creationAttempted,
            context=current,changes=ContextContract.Differences(before,current),metadata=ReadMetadata(),
            scalarGroupRole="diagnostic only: not an ownership certificate",realGroups=NativeLevelGroups.Capture(),entityCountIncludingBlanked=LevelsManager.GetLevelEntityCount(target,true)});
    }
    void RequireMetadataOwnership()=>LevelGroupContract.RequireOwned(target,existed,metadata.Name,ReadMetadata().Name,groups,NativeLevelGroups.Capture());
    void RequireOwnedDelta(string current)
    {
        ContextContract.PlanRollback(before,current,target);
        RequireMetadataOwnership();
    }
    internal void PrepareCommit()
    {
        Observe("before-output-level-commit-reconciliation");string current=NativeBoundary.ContextSeal();RequireOwnedDelta(current);
        BoundaryKernel.Require(ContextContract.Levels(current,"activeLevels").Contains(target),"Output level absent after writing geometry.");
        bool wanted=existed?ContextContract.Levels(before,"visibleLevels").Contains(target):true;
        if(ContextContract.Levels(current,"visibleLevels").Contains(target)!=wanted)
            BoundaryKernel.Require(LevelsManager.SetLevelVisible(target,wanted),"Could not restore the specified output level visibility.");
        NativeBoundary.VerifyContext(ContextContract.ExpectedCommitted(before,target));
        RequireMetadataOwnership();
        NativeBoundary.Record("output-level-commit-context-verified",new{target,createdLevel=!existed,visible=wanted,expected=ContextContract.ExpectedCommitted(before,target)},verified:true);
    }
    internal void RestoreAfterRollback()
    {
        Observe("after-cancel-before-level-restoration");string current=NativeBoundary.ContextSeal();RequireOwnedDelta(current);
        var repair=ContextContract.PlanRollback(before,current,target);
        BoundaryKernel.Require(creationAttempted||(!repair.DeleteNewEmptyLevel&&!repair.RestoreExistingVisibility),"No output write was attempted; refusing ownership of a level change.");
        if(repair.DeleteNewEmptyLevel)
        {
            BoundaryKernel.Require(creationAttempted&&!existed&&target!=SettingsManager.MainLevel,"Refusing deletion of an unowned or main level.");
            BoundaryKernel.Require(LevelsManager.GetLevelEntityCount(target,true)==0&&!NativeBoundary.Inventory().Any(g=>g.Level==target),"Output level is not empty, including blanked geometry; refusing deletion.");
            bool deleted=LevelsManager.DeleteLevel(target);
            NativeBoundary.Record("owned-empty-output-level-delete",new{target,returned=deleted},verified:null);
            BoundaryKernel.Require(deleted,"Public DeleteLevel did not report deletion of the owned empty output level.");
        }
        else if(repair.RestoreExistingVisibility)
        {
            BoundaryKernel.Require(LevelsManager.SetLevelVisible(target,repair.ExpectedVisibility),"Existing output level visibility restoration failed.");
            NativeBoundary.Record("existing-output-level-visibility-restored",new{target,visible=repair.ExpectedVisibility},verified:null);
        }
        NativeBoundary.VerifyContext(before);
        BoundaryKernel.Require(LevelsManager.GetLevelEntityCount(target,true)==beforeEntityCount,"Output level count did not restore.");
        RequireMetadataOwnership();Observe("after-output-level-restoration");NativeBoundary.VerifyContext(before);
        NativeBoundary.Record("output-level-restoration-verified",new{target,existedBefore=existed,deletedNewEmptyLevel=repair.DeleteNewEmptyLevel,restoredExistingVisibility=repair.RestoreExistingVisibility},verified:true);
    }
}
