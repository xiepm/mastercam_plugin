using System;
using System.Linq;

namespace MastercamPluginAI.EdgeAdapter;

/// <summary>Read-only admission. This candidate never creates or reveals an output level.</summary>
public static class OutputLevelAdmission
{
    public const string Rejection="Output requires an existing visible level; 仅允许已有可见输出层";
    public static int[] Eligible(string context)
    {
        var active=ContextContract.Levels(context,"activeLevels");
        var visible=ContextContract.Levels(context,"visibleLevels");
        BoundaryKernel.Require(active.All(n=>n<=999999)&&visible.All(active.Contains),"Invalid active/visible output level inventory.");
        return visible;
    }
    public static void RequireExistingVisible(string context,int target)
    {
        BoundaryKernel.Require(target>=1&&target<=999999,"Invalid output level identity.");
        BoundaryKernel.Require(Eligible(context).Contains(target),Rejection+": "+target);
    }
}
