#r "__SYSTEM_TEXT_JSON__"
using System;using System.IO;using System.Linq;using System.Runtime.InteropServices;using System.Text.Json;
// Microsoft CLR hosting interfaces: metahost.idl and mscoree.idl.
// Reuse the already loaded CLR v4. Never start/stop or create another runtime.
if(!Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName).Equals(__MODEL__,StringComparison.OrdinalIgnoreCase))throw new Exception("Wrong document");
if(Hash(__MODEL__)!=__MODEL_SHA__||Hash(__REQUEST__)!=__REQUEST_SHA__||Hash(__DLL__)!=__DLL_SHA__)throw new Exception("Binding changed");
if(Mastercam.Support.SearchManager.GetOperations().Length!=9||Mastercam.Support.SearchManager.GetOperations().Any(o=>o.Dirty))throw new Exception("Invalid operations");
var meta=(IClrMetaHost)CreateMeta();var infoGuid=new Guid("BD39D1D2-BA2F-486a-89B0-B4B0CB466891");object runtime;
Marshal.ThrowExceptionForHR(meta.GetRuntime("v4.0.30319",ref infoGuid,out runtime));
var info=(IClrRuntimeInfo)runtime;bool loaded;Marshal.ThrowExceptionForHR(info.IsLoaded(System.Diagnostics.Process.GetCurrentProcess().Handle,out loaded));if(!loaded)throw new Exception("Verify CLR is not loaded");
var hostClass=new Guid("90F1A06E-7712-4762-86B5-7A5EBA6BDB02");var hostInterface=new Guid("90F1A06C-7712-4762-86B5-7A5EBA6BDB02");object host;
Marshal.ThrowExceptionForHR(info.GetInterface(ref hostClass,ref hostInterface,out host));
uint result;Marshal.ThrowExceptionForHR(((IClrRuntimeHost)host).ExecuteInDefaultAppDomain(__DLL__,"SimulationFrameworkEntry","Dispatch",__REQUEST__,out result));if(result!=0)throw new Exception("Framework dispatch failed; inspect dispatch receipt");
string Hash(string p){return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();}
object CreateMeta(){var cls=new Guid("9280188D-0E8E-4867-B30C-7FA83884E8DE");var iid=new Guid("D332DB9E-B9B3-4125-8207-A14884F53216");object o;Marshal.ThrowExceptionForHR(ClrApi.CLRCreateInstance(ref cls,ref iid,out o));return o;}
public static class ClrApi{[DllImport("mscoree.dll",ExactSpelling=true)]public static extern int CLRCreateInstance(ref Guid cls,ref Guid iid,[MarshalAs(UnmanagedType.IUnknown)]out object result);}
[ComImport,Guid("D332DB9E-B9B3-4125-8207-A14884F53216"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IClrMetaHost{[PreserveSig]int GetRuntime([MarshalAs(UnmanagedType.LPWStr)]string version,ref Guid iid,[MarshalAs(UnmanagedType.IUnknown)]out object runtime);}
[ComImport,Guid("BD39D1D2-BA2F-486a-89B0-B4B0CB466891"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IClrRuntimeInfo{
 void GetVersionString();void GetRuntimeDirectory();[PreserveSig]int IsLoaded(IntPtr process,[MarshalAs(UnmanagedType.Bool)]out bool loaded);void LoadErrorString();void LoadLibrary();void GetProcAddress();
 [PreserveSig]int GetInterface(ref Guid cls,ref Guid iid,[MarshalAs(UnmanagedType.IUnknown)]out object result);
}
[ComImport,Guid("90F1A06C-7712-4762-86B5-7A5EBA6BDB02"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IClrRuntimeHost{
 void Start();void Stop();void SetHostControl();void GetCLRControl();void UnloadAppDomain();void ExecuteInAppDomain();void GetCurrentAppDomainId();void ExecuteApplication();
 [PreserveSig]int ExecuteInDefaultAppDomain([MarshalAs(UnmanagedType.LPWStr)]string assembly,[MarshalAs(UnmanagedType.LPWStr)]string type,[MarshalAs(UnmanagedType.LPWStr)]string method,[MarshalAs(UnmanagedType.LPWStr)]string argument,out uint result);
}
