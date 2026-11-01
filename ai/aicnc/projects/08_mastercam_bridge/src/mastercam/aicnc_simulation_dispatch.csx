#r "System.Web.Extensions"
// Do not #r the side-loaded bridge: the NET-Script loader does not resolve it
// reliably at runtime. Bind the exact assembly explicitly in a scoped resolver.
var result=new System.Collections.Generic.Dictionary<string,object>();
result["ok"]=false;
System.ResolveEventHandler resolver=null;
ICorRuntimeHost host=null;
System.IntPtr enumeration=System.IntPtr.Zero;
try {
    if(!System.String.Equals(System.IO.Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName),System.IO.Path.GetFullPath(__MODEL__),System.StringComparison.OrdinalIgnoreCase)) throw new System.Exception("Active document changed");
    var ops=Mastercam.Support.SearchManager.GetOperations();
    var request=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(System.IO.File.ReadAllText(__REQUEST_PATH__));
    var names=new System.Collections.Generic.List<string>();
    if(request.ContainsKey("operations"))foreach(System.Collections.Generic.Dictionary<string,object> op in (System.Collections.IEnumerable)request["operations"])names.Add((string)op["operation_name"]);
    else names.Add(__OP_NAME__);
    if(ops.Length!=names.Count)throw new System.Exception("Operation count changed");
    for(int i=0;i<ops.Length;i++)if(ops[i].Name!=names[i]||ops[i].Dirty)throw new System.Exception("Operation/order changed");
    if(Hash(__MODEL__)!=__MODEL_SHA__ || Hash(__REQUEST_PATH__)!=__REQUEST_SHA__)throw new System.Exception("Model/request hash changed");
    string path=__DLL_PATH__;
    using(var sha=System.Security.Cryptography.SHA256.Create())
    using(var stream=System.IO.File.OpenRead(path))
        if(System.BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant()!=__DLL_SHA__)
            throw new System.Exception("Bridge DLL hash mismatch");
    var helper=System.Reflection.Assembly.LoadFrom(path);
    resolver=(sender,args)=>args.Name==helper.FullName?helper:null;
    System.AppDomain.CurrentDomain.AssemblyResolve+=resolver;
    host=(ICorRuntimeHost)System.Runtime.InteropServices.RuntimeEnvironment.GetRuntimeInterfaceAsObject(
        new System.Guid("CB2F6723-AB3A-11d2-9C40-00C04FA30A3E"),
        new System.Guid("CB2F6722-AB3A-11d2-9C40-00C04FA30A3E"));
    System.Runtime.InteropServices.Marshal.ThrowExceptionForHR(host.EnumDomains(out enumeration));
    object domainObject; System.AppDomain selected=null;
    while(host.NextDomain(enumeration,out domainObject)==0 && domainObject!=null) {
        var domain=(System.AppDomain)domainObject;
        if(domain.FriendlyName!="UBVS AppDomain")continue;
        if(selected!=null)throw new System.Exception("Multiple simulator domains");
        selected=domain;
    }
    if(selected==null)throw new System.Exception("No Simulator domain");
    {
        var proxy=selected.CreateInstanceFromAndUnwrap(path,"SimulationDomainBridge");
        var method=proxy.GetType().GetMethod("Dispatch");
        if(method==null)throw new System.Exception("Cross-domain bridge type did not resolve");
        result["status"]=method.Invoke(proxy,new object[]{__ACTION__,__RECEIPT__,__MODEL__,__ARTIFACT__});
    }
    result["request_sha256"]=__REQUEST_SHA__; result["model_sha256"]=__MODEL_SHA__; result["pid"]=System.Diagnostics.Process.GetCurrentProcess().Id;
    result["ok"]=true;
} catch(System.Exception error) {result["error"]=error.ToString();}
finally {
    if(host!=null && enumeration!=System.IntPtr.Zero)host.CloseEnum(enumeration);
    if(resolver!=null)System.AppDomain.CurrentDomain.AssemblyResolve-=resolver;
}
using(var stream=new System.IO.FileStream(__DISPATCH__,System.IO.FileMode.CreateNew))
using(var writer=new System.IO.StreamWriter(stream))
    writer.Write(new System.Web.Script.Serialization.JavaScriptSerializer().Serialize(result));

string Hash(string path) { using(var sha=System.Security.Cryptography.SHA256.Create()) using(var stream=System.IO.File.OpenRead(path)) return System.BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }

[System.Runtime.InteropServices.ComImport,
System.Runtime.InteropServices.Guid("CB2F6722-AB3A-11d2-9C40-00C04FA30A3E"),
System.Runtime.InteropServices.InterfaceType(System.Runtime.InteropServices.ComInterfaceType.InterfaceIsIUnknown)]
public interface ICorRuntimeHost {
    void CreateLogicalThreadState(); void DeleteLogicalThreadState();
    void SwitchInLogicalThreadState(System.IntPtr p); void SwitchOutLogicalThreadState(out System.IntPtr p);
    void LocksHeldByLogicalThread(out uint p); void MapFile(System.IntPtr f,out System.IntPtr p);
    void GetConfiguration(out System.IntPtr p); void Start(); void Stop();
    void CreateDomain(string n,object i,out object d); void GetDefaultDomain(out object d);
    [System.Runtime.InteropServices.PreserveSig] int EnumDomains(out System.IntPtr h);
    [System.Runtime.InteropServices.PreserveSig] int NextDomain(System.IntPtr h,
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.IUnknown)] out object d);
    [System.Runtime.InteropServices.PreserveSig] int CloseEnum(System.IntPtr h);
}
