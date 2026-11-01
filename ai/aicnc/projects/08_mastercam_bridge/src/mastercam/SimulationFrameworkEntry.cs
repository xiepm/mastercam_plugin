// Mastercam 2027 hosts NET-Script in .NET 10, but Verify still uses CLR v4.
// Called only inside the owning Mastercam process through the CLR hosting API.
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Web.Script.Serialization;

public static class SimulationFrameworkEntry {
 public static int Dispatch(string requestPath) {
  var json=new JavaScriptSerializer();
  var req=json.Deserialize<Dictionary<string,string>>(File.ReadAllText(requestPath));
  var result=new Dictionary<string,object>{{"ok",false},{"runtime",Environment.Version.ToString()}};
  ICorRuntimeHost host=null;IntPtr enumeration=IntPtr.Zero;
  var assembly=Assembly.GetExecutingAssembly();
  ResolveEventHandler resolver=(sender,args)=>args.Name==assembly.FullName?assembly:null;
  AppDomain.CurrentDomain.AssemblyResolve+=resolver;
  try {
   host=(ICorRuntimeHost)RuntimeEnvironment.GetRuntimeInterfaceAsObject(new Guid("CB2F6723-AB3A-11d2-9C40-00C04FA30A3E"),new Guid("CB2F6722-AB3A-11d2-9C40-00C04FA30A3E"));
   Marshal.ThrowExceptionForHR(host.EnumDomains(out enumeration));
   object obj;AppDomain selected=null;
   while(host.NextDomain(enumeration,out obj)==0&&obj!=null){var d=(AppDomain)obj;if(d.FriendlyName!="UBVS AppDomain")continue;if(selected!=null)throw new Exception("Multiple simulator domains");selected=d;}
   if(selected==null)throw new Exception("No UBVS AppDomain");
   var proxy=selected.CreateInstanceFromAndUnwrap(Assembly.GetExecutingAssembly().Location,"SimulationDomainBridge");
   result["proxy_type"]=proxy.GetType().AssemblyQualifiedName;
   var method=proxy.GetType().GetMethod("Dispatch");
   if(method==null)throw new Exception("Simulator bridge method did not resolve");
   // This entry is restricted by P08's source hash and 18x18x10 mm stock profile.
   // An absolute factor avoids drift from rescaling the previous session's factor.
   proxy.GetType().GetMethod("SetDiagnosticProfile").Invoke(proxy,new object[]{0.005f,0.02f,1,5.662441f});
   result["status"]=method.Invoke(proxy,new object[]{req["action"],req["receipt"],req["model"],req["artifact"]});
   result["ok"]=true;
  }catch(Exception e){result["error"]=e.ToString();}
  finally{if(host!=null&&enumeration!=IntPtr.Zero)host.CloseEnum(enumeration);AppDomain.CurrentDomain.AssemblyResolve-=resolver;}
  using(var f=new FileStream(req["dispatch_receipt"],FileMode.CreateNew))using(var w=new StreamWriter(f))w.Write(json.Serialize(result));
  return (bool)result["ok"]?0:1;
 }
 [ComImport,Guid("CB2F6722-AB3A-11d2-9C40-00C04FA30A3E"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 public interface ICorRuntimeHost {
  void CreateLogicalThreadState();void DeleteLogicalThreadState();void SwitchInLogicalThreadState(IntPtr p);void SwitchOutLogicalThreadState(out IntPtr p);void LocksHeldByLogicalThread(out uint p);void MapFile(IntPtr f,out IntPtr p);void GetConfiguration(out IntPtr p);void Start();void Stop();void CreateDomain(string n,object i,out object d);void GetDefaultDomain(out object d);
  [PreserveSig]int EnumDomains(out IntPtr h);
  [PreserveSig]int NextDomain(IntPtr h,[MarshalAs(UnmanagedType.IUnknown)]out object d);
  [PreserveSig]int CloseEnum(IntPtr h);
 }
}
