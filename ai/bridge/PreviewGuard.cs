using System;
namespace MastercamPluginAI;

// The approved representation never changes. Any failed rebuild consumes this guard.
public sealed class PreviewGuard
{
    public string Approved { get; }
    public bool IsValid { get; private set; } = true;
    public PreviewGuard(string approved) { Approved = approved ?? throw new ArgumentNullException(nameof(approved)); }
    public T Rebuild<T>(Func<T> build, Func<T,string> serialize)
    {
        if(!IsValid) throw new InvalidOperationException("Preview invalidated; prepare a new plan.");
        try {
            T candidate=build();
            if(!string.Equals(Approved,serialize(candidate),StringComparison.Ordinal))
                throw new InvalidOperationException("Rebuilt preview changed; prepare a new plan.");
            return candidate;
        } catch { IsValid=false; throw; }
    }
}
