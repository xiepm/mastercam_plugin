using Mastercam.IO;
namespace MastercamPluginAI.EdgeAdapter;
// Existing levels only. No level/group creation, deletion, refresh or guessed ownership.
internal sealed class NativeOutputLevelLease
{
    readonly int target;readonly string context;readonly int count;
    internal NativeOutputLevelLease(int level,string before)
    {
        target=level;context=before;OutputLevelAdmission.RequireExistingVisible(before,level);
        NativeBoundary.VerifyContext(before);count=LevelsManager.GetLevelEntityCount(level,true);
    }
    internal void PrepareCommit(){OutputLevelAdmission.RequireExistingVisible(NativeBoundary.ContextSeal(),target);NativeBoundary.VerifyContext(context);}
    internal void RestoreAfterRollback()
    {
        NativeBoundary.VerifyContext(context);
        BoundaryKernel.Require(LevelsManager.GetLevelEntityCount(target,true)==count,"已有输出层实体数未恢复。");
    }
}
