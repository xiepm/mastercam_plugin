using System;
using System.IO;
using System.Linq;
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
    static bool started, workshop, bee, middle, ipc;
    static NetHook3App agentHook;
    static int attempts;
    public override int Version(int p) => (int)MCamDefines.NetHookLibraryVersion;
    public override MCamReturn Init(int p)
    {
        try
        {
            string root = AgentRoot();
            if (root != null && !PreviousUsesIpc())
            {
                var assembly = System.Reflection.Assembly.LoadFrom(Path.Combine(root, "chooks", "MCNetScripting", "IPCServer.dll"));
                agentHook = (NetHook3App)Activator.CreateInstance(assembly.GetType("IPCServer.Main", true));
                agentHook.Init(p);
            }
        }
        catch (Exception e) { Log("Agent IPC init: " + e); }
        return MCamReturn.NoErrors;
    }
    public override MCamReturn Run(int p)
    {
        if (started) return MCamReturn.NoErrors;
        started = true;
        if (agentHook == null) Init(p);
        TryStartAgent();
        // The installer creates this FT only when there was a previous startup hook.
        string chooks = Directory.GetParent(Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)).FullName;
        if (File.Exists(Path.Combine(chooks, "MC2027SuitePrevious.ft")))
            try
            {
                bool previous = ExternalAppsManager.RunFTCommand("MC2027SuitePrevious", "Run");
                Log("Previous startup: " + previous);
                if (previous && PreviousUsesIpc()) ipc = true;
            }
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
            TryStartAgent();
            if (!bee) bee = ExternalAppsManager.RunFTCommand("LittleBee2027", "InstallRibbon");
            if (!workshop) workshop = ExternalAppsManager.RunFTCommand("Workshop2027", "InstallRibbon");
            if (!middle) middle = ExternalAppsManager.RunFTCommand("MiddleConfirm2027", "Start");
            Log($"Attempt={attempts}, LittleBee={bee}, Workshop={workshop}, Middle={middle}, IPC={ipc}");
            if (bee && workshop && middle && ipc) Stop();
        }
        catch (Exception e) { Log(e.ToString()); }
    }
    static void TryStartAgent()
    {
        if (ipc) return;
        try
        {
            if (AgentRoot() == null) ipc = true;
            else if (agentHook != null)
            {
                string pipe = "MastercamPipe" + System.Diagnostics.Process.GetCurrentProcess().Id;
                if (Directory.GetFiles(@"\\.\pipe\").Any(p => p.EndsWith(pipe, StringComparison.OrdinalIgnoreCase))) ipc = true;
                else ipc = agentHook.Run(0) == MCamReturn.NoErrors;
            }
        }
        catch (Exception e) { Log("Agent IPC startup: " + e); }
    }
    static bool PreviousUsesIpc()
    {
        string chooks = Directory.GetParent(Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)).FullName;
        string path = Path.Combine(chooks, "MC2027SuitePrevious.ft");
        return File.Exists(path) && File.ReadAllText(path).IndexOf("IPCServer.dll", StringComparison.OrdinalIgnoreCase) >= 0;
    }
    static string AgentRoot()
    {
        string marker = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MC2027PluginSuite", "agent-enabled.json");
        if (!File.Exists(marker)) return null;
        using var config = System.Text.Json.JsonDocument.Parse(File.ReadAllText(marker));
        string install = Directory.GetParent(Directory.GetParent(Path.GetDirectoryName(typeof(StartupHook).Assembly.Location)).FullName).FullName;
        bool enabled = config.RootElement.GetProperty("enabled").GetBoolean();
        string expected = config.RootElement.GetProperty("mastercam_root").GetString();
        return enabled && string.Equals(Path.GetFullPath(expected).TrimEnd('\\'), Path.GetFullPath(install).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase) ? install : null;
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
