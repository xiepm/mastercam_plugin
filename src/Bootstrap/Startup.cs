using System;
using System.IO;
using System.Windows.Forms;
using Mastercam.App;
using Mastercam.App.Types;
using Mastercam.Support;
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: System.Runtime.Versioning.TargetFramework(".NETCoreApp,Version=v10.0")]
namespace MC2027Suite.Bootstrap;
public sealed class StartupHook : NetHook3App
{
    static Timer timer;
    static bool started, workshop, bee, middle;
    static int attempts;
    public override int Version(int p) => (int)MCamDefines.NetHookLibraryVersion;
    public override MCamReturn Init(int p) => MCamReturn.NoErrors;
    public override MCamReturn Run(int p)
    {
        if (started) return MCamReturn.NoErrors;
        started = true;
        // The installer creates this FT only when there was a previous startup hook.
        string chooks = Directory.GetParent(Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)).FullName;
        if (File.Exists(Path.Combine(chooks, "MC2027SuitePrevious.ft")))
            try { Log("Previous startup: " + ExternalAppsManager.RunFTCommand("MC2027SuitePrevious", "Run")); }
            catch (Exception e) { Log("Previous startup error: " + e); }
        timer = new Timer { Interval = 1000 };
        timer.Tick += Tick;
        timer.Start();
        return MCamReturn.NoErrors;
    }
    static void Tick(object sender, EventArgs args)
    {
        if (++attempts > 5) { Stop(); Log("Startup registration retries exhausted."); return; }
        try
        {
            var owner = Mastercam.UI.MastercamWindow.GetHandle();
            if (owner == null || owner.Handle == IntPtr.Zero) return;
            if (!bee) bee = ExternalAppsManager.RunFTCommand("LittleBee2027", "InstallRibbon");
            if (!workshop) workshop = ExternalAppsManager.RunFTCommand("Workshop2027", "InstallRibbon");
            if (!middle) middle = ExternalAppsManager.RunFTCommand("MiddleConfirm2027", "Start");
            Log($"Attempt={attempts}, LittleBee={bee}, Workshop={workshop}, Middle={middle}");
            if (bee && workshop && middle) Stop();
        }
        catch (Exception e) { Log(e.ToString()); }
    }
    static void Stop() { if (timer != null) { timer.Stop(); timer.Tick -= Tick; timer.Dispose(); timer = null; } }
    static void Log(string message)
    {
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MC2027PluginSuite");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "startup.log"), DateTime.Now.ToString("s") + " " + message + Environment.NewLine);
        }
        catch { }
    }
    public override MCamReturn Close(int p) { Stop(); return MCamReturn.NoErrors; }
    public override MCamReturn Notify(MCamEvent e) { if (e == MCamEvent.AppExit) Stop(); return MCamReturn.NoErrors; }
}
