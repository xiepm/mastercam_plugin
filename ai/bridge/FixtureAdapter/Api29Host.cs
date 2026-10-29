using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using FixtureTools2027.Core;
using Mastercam.BasicGeometry;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.Database.Types;
using Mastercam.IO;
using Mastercam.Math;
using Mastercam.Support;

namespace MastercamPluginAI.FixtureAdapter;

public static class FixtureApi
{
    /// <summary>Call only inside Mastercam's synchronous UI-thread NET-Hook/NET-Script callback.</summary>
    public static FixtureSession OpenSession() => new(new Api29Host());
    public static NativeFixtureSession OpenNativeSession() => NativeFixtureCopy.OpenSession();
    public static long ContextEpoch => System.Threading.Interlocked.Read(ref epoch);
    private static long epoch;
    internal static void InvalidateContext() => System.Threading.Interlocked.Increment(ref epoch);
    [ThreadStatic] private static bool ownedBoundary;
    [ThreadStatic] private static int ownedUndoNotifications;
    internal static int OwnedUndoNotifications => ownedUndoNotifications;
    internal static bool ObserveOwnedUndo()
    {
        if(!ownedBoundary)return false;
        ownedUndoNotifications++;return true;
    }
    internal static void OwnedBoundary(Action action)
    {
        if(ownedBoundary)throw new FixtureException("Reentrant transaction boundary refused.");
        ownedBoundary=true;try {action();}finally {ownedBoundary=false;}
    }
}

internal sealed class Api29Host : IFixtureHost
{
    private readonly string token=Guid.NewGuid().ToString("N");
    private readonly uint thread;
    private readonly int managedThread;
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
    internal Api29Host()
    {
        if(!string.Equals(Process.GetCurrentProcess().ProcessName,"Mastercam",StringComparison.OrdinalIgnoreCase))
            throw new FixtureException("Host adapter is restricted to Mastercam. Offline code must reference Core only.");
        var window=Mastercam.UI.MastercamWindow.GetHandle();
        if(window==null||window.Handle==IntPtr.Zero) throw new FixtureException("Mastercam main window is unavailable.");
        thread=GetWindowThreadProcessId(window.Handle,out uint process);
        if(process!=(uint)Environment.ProcessId||thread!=GetCurrentThreadId()) throw new FixtureException("Must be called on the Mastercam main window thread.");
        managedThread=Environment.CurrentManagedThreadId;
    }
    public void AssertHostThread()
    {
        if(Environment.CurrentManagedThreadId!=managedThread||GetCurrentThreadId()!=thread) throw new FixtureException("Worker-thread host access refused; parent must invoke synchronously on host thread.");
    }
    public DocumentStamp Document { get { AssertHostThread(); return new(token,FixtureApi.ContextEpoch,FileManager.CurrentFileName??"",SettingsManager.Metric?"mm":"inch"); } }
    public bool TransactionActive { get { AssertHostThread(); return UndoManager.IsTransactionActive(); } }
    public bool StartTransaction() { AssertHostThread(); return UndoManager.StartTransaction(); }
    public void CommitTransaction() { AssertHostThread(); FixtureApi.OwnedBoundary(UndoManager.CommitTransaction); }
    public void CancelTransaction() { AssertHostThread(); FixtureApi.OwnedBoundary(UndoManager.CancelTransaction); }
    public string[] BoundaryDiagnostics => new[] {"Owned synchronous commit/cancel Undo notifications observed on this thread: "+FixtureApi.OwnedUndoNotifications+". These alone do not change document epoch; full readback still required."};
    public int[] SelectedIds()
    { AssertHostThread(); return SearchManager.GetSelectedGeometry().Select(e=>e.GetEntityID()).Distinct().ToArray(); }
    private static Vec3 V(Point3D p) => new(p.x,p.y,p.z);
    private static Point3D P(Vec3 p) => new(p.X,p.Y,p.Z);
    public IReadOnlyList<EntityReadback> ReadDocument()
    {
        AssertHostThread();
        // Both visible/alive and blanked queries: never reveal, select, or commit existing geometry.
        var visible=SearchManager.GetGeometry(new GeometryMask(true),new SelectionMask(true,false,false),-1);
        var blanked=SearchManager.GetGeometry(new GeometryMask(true),new SelectionMask(true,false,true),-1);
        if(visible==null||blanked==null) throw new FixtureException("Host inventory returned null.");
        var ids=visible.Concat(blanked).Select(e=>e.GetEntityID()).Distinct().OrderBy(i=>i).ToArray();
        if(ids.Length>200000) throw new FixtureException("Document exceeds the bounded inventory limit.");
        var result=new List<EntityReadback>(ids.Length);
        foreach(int id in ids)
        {
            var g=Geometry.RetrieveEntity(id);
            if(g==null||!g.Retrieve()) throw new FixtureException("Unable to read entity "+id);
            EntitySpec? shape=null;
            // Exact type checks reject associative subclasses whose dependency data is not serialized.
            if(g.GetType()==typeof(PointGeometry)) shape=new() { Kind="point", A=V(((PointGeometry)g).Data), Level=g.Level, Color=g.Color };
            else if(g.GetType()==typeof(LineGeometry)) { var line=(LineGeometry)g; shape=new() { Kind="line", A=V(line.EndPoint1), B=V(line.EndPoint2), Level=g.Level, Color=g.Color }; }
            result.Add(new(id,g.GetType().FullName??g.GetType().Name,g.Level,g.Color,g.Selected,g.Blanked,shape));
        }
        return result;
    }
    public int Create(EntitySpec spec)
    {
        AssertHostThread(); spec.Validate();
        if(!TransactionActive) throw new FixtureException("Creation requires an active owned transaction.");
        Geometry g=spec.Kind=="point"?new PointGeometry(P(spec.A)):new LineGeometry(P(spec.A),P(spec.B!.Value));
        if(g.GetEntityID()>0) throw new FixtureException("Constructor unexpectedly returned a committed entity.");
        g.Level=spec.Level; g.Color=spec.Color; g.Selected=false; g.Blanked=false;
        if(!g.Commit()) throw new FixtureException("New entity Commit returned false; owned transaction must roll back.");
        return g.GetEntityID();
    }
}
