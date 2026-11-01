#r "__SYSTEM_TEXT_JSON__"
using System;using System.IO;using System.Linq;using System.Text.Json;
using Mastercam.IO;using Mastercam.Support;
new SaveStandViews().Run(__MODEL__,__MODEL_SHA__,__RECEIPT__);
public class SaveStandViews {
 public void Run(string model,string expectedHash,string receipt){
  if(File.Exists(receipt))throw new Exception("Receipt exists");
  bool ok=false;string error=null;
  try{
   if(Path.GetFullPath(FileManager.CurrentFileName)!=Path.GetFullPath(model))throw new Exception("Wrong document");
   if(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(model))).ToLowerInvariant()!=expectedHash)throw new Exception("Saved model changed");
   if(ViewSheets.GetSheetCount()!=2||ViewSheets.GetViewSheetName(0)!="装夹1_正面_G54"||ViewSheets.GetViewSheetName(1)!="装夹2_翻面_G55")throw new Exception("View names not committed");
   if(SearchManager.GetOperations().Length!=9||SearchManager.GetOperations().Any(o=>o.Dirty))throw new Exception("Operation state changed");
   // UI submits tab names. Save through the native API so imported STEP UI
   // state cannot leave an asynchronous Save As dialog behind.
   if(!ViewSheets.SetActiveViewSheet(0))throw new Exception("First setup view missing");
   var top=ViewManager.GetAllViews(true).Single(v=>v.ViewName=="S1_TOP_G54");
   ViewManager.WorkCoordinateSystem=top;ViewManager.TPlane=top;ViewManager.CPlane=top;ViewManager.GraphicsView=top;
   if(!ViewSheets.SaveBookmark(0)||!FileManager.Save())throw new Exception("Save failed");
   ok=true;
  }catch(Exception e){error=e.ToString();}
  File.WriteAllText(receipt,JsonSerializer.Serialize(new{ok,error,pid=Environment.ProcessId,model,
    model_sha256=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(model))).ToLowerInvariant(),
    ui_tab_names_required=true,production_released=false}));
 }
}
