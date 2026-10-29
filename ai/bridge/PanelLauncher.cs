using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Windows.Forms;
using Mastercam.IO;
using Mastercam.Support;
namespace MastercamPluginAI;
internal static class PanelLauncher
{
    static Timer pending;
    static bool queued;
    static readonly HashSet<string> Modules=new(StringComparer.OrdinalIgnoreCase){"AdvancedDrill2027","AdvancedDrillTap2027","SolidBoundary2027","ChainTools2027","LittleBee2027","GeometryTools2027.NativeCommands","MiddleConfirm2027","GeometryTools2027"};
    internal static bool Busy=>queued||Application.OpenForms.Cast<Form>().Any(f=>f.Visible&&Modules.Contains(f.GetType().Assembly.GetName().Name));
    internal static string Queue(string application,string function,string directory)
    {
        if(Busy)throw new InvalidOperationException("A plugin panel is queued or open; close it before another command.");
        if(UndoManager.IsTransactionActive())throw new InvalidOperationException("Finish the existing native transaction first.");
        string document=FileManager.CurrentFileName,path=Path.Combine(directory,"panel-status.json");Directory.CreateDirectory(directory);
        void Save(string status,bool? returned=null,string error=null)=>File.WriteAllText(path,JsonSerializer.Serialize(new{status,application,function,returned,error,business_completed=false}));
        Save("queued");queued=true;pending=new Timer{Interval=100};
        pending.Tick+=(sender,args)=>{
            pending.Stop();pending.Dispose();pending=null;
            try{
                if(!string.Equals(document,FileManager.CurrentFileName,StringComparison.OrdinalIgnoreCase)||UndoManager.IsTransactionActive())throw new InvalidOperationException("Document/transaction changed before panel dispatch.");
                Save("dispatching");bool returned=ExternalAppsManager.RunFTCommand(application,function);Save(returned?"returned":"dispatch_failed",returned);
            }catch(Exception e){Save("dispatch_failed",null,e.ToString());}finally{queued=false;}
        };
        pending.Start();return path;
    }
}
