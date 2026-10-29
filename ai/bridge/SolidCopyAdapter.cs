using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Mastercam.Database;
using Mastercam.Support;

namespace MastercamPluginAI;
using PorscheAdvanced2027;

internal static class SolidCopyAdapter
{
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)]static extern IntPtr GetProcAddress(IntPtr handle,string name);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int BodyTagDelegate(int faceTag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr EptrDelegate(IntPtr returnStorage,int bodyTag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int TagFromDbIdDelegate(IntPtr dbId);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int DeleteFacesDelegate(IntPtr vector,IntPtr options,IntPtr tracking);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int CopyKernelDelegate(int source,IntPtr options,out int copy,IntPtr tracking);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void FreeTrackingDelegate(IntPtr tracking);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int DeleteKernelDelegate(int count,ref int tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr CreateEntityDelegate(IntPtr result,int body,byte blank);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate void CreateBodyHistoryDelegate(IntPtr dbId);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)][return:MarshalAs(UnmanagedType.I1)]delegate bool RemoveHistoryDelegate(IntPtr arrayView);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)][return:MarshalAs(UnmanagedType.I1)]delegate bool DetectDelegate(int body,IntPtr parameters,out int count,ref byte showInvalidBodyMessage);
    const string NativeHash="C73D6C39B110EC708D0989650DAFB8E1AA778D57B86ED8ED4ABADED263B85038";
    static IntPtr Module()
    {
        var path=Path.Combine(Path.GetDirectoryName(typeof(SolidGeometry).Assembly.Location),"MCGeomSld.dll");using(var stream=File.OpenRead(path))if(Convert.ToHexString(SHA256.HashData(stream))!=NativeHash)throw new InvalidOperationException("当前原生几何库版本未经此适配器验证。");
        var module=GetModuleHandle("MCGeomSld.dll");if(module==IntPtr.Zero)throw new InvalidOperationException("原生几何库尚未加载。");return module;
    }
    static T Get<T>(IntPtr module,string symbol)where T:Delegate{var ptr=GetProcAddress(module,symbol);if(ptr==IntPtr.Zero)throw new MissingMethodException(symbol);return Marshal.GetDelegateForFunctionPointer<T>(ptr);}
    internal static SolidGeometry CopyIndependent(int sourceId)
    {
        using var selection=new GeometrySelection();
        var module=Module();var kernel=GetModuleHandle("PSKERNEL.dll");if(kernel==IntPtr.Zero)throw new InvalidOperationException("几何内核未加载。");
        using(var stream=File.OpenRead(Path.Combine(Path.GetDirectoryName(typeof(SolidGeometry).Assembly.Location),"PSKERNEL.dll")))if(Convert.ToHexString(SHA256.HashData(stream))!="44B9A90D60DB1ED231D171EBAD1BC68EED79B39DFB2088D8E3B341E57FD148A5")throw new NotSupportedException("几何复制接口构建不符。");
        var source=Geometry.RetrieveEntity(sourceId);var baseline=GeometrySelection.All().Select(g=>g.GetEntityID()).ToHashSet();
        int body=Get<BodyTagDelegate>(module,"?ps_get_body_tag@@YAHH@Z")(SearchManager.GetFaceTagsAndPidMapFromBodyEntity(sourceId).Values.First());
        IntPtr options=Marshal.AllocHGlobal(32),tracking=Marshal.AllocHGlobal(40),result=Marshal.AllocHGlobal(8);int copy=0;bool transferred=false;
        try
        {
            Marshal.Copy(new byte[32],0,options,32);Marshal.WriteInt32(options,2);Marshal.Copy(new byte[40],0,tracking,40);Marshal.WriteInt64(result,0);
            // PK_ENTITY_copy_2 v2 layout and four-argument ABI observed in the
            // native remove-history path. No source database transform or rewrite.
            int status=Get<CopyKernelDelegate>(kernel,"PK_ENTITY_copy_2")(body,options,out copy,tracking);
            if(status!=0||copy<=0||copy==body)throw new InvalidOperationException("独立实体复制失败，状态="+status);
            Get<CreateEntityDelegate>(module,"?sld_solid_from_tag@@YA?AVDbId@Database@Lib@Cnc@@H_N@Z")(result,copy,0);
            IntPtr dbId=Marshal.ReadIntPtr(result);if(dbId==IntPtr.Zero)throw new InvalidOperationException("副本数据库实体创建失败。");transferred=true;
            Get<CreateBodyHistoryDelegate>(module,"?mc_create_body_op@@YAXVDbId@Database@Lib@Cnc@@@Z")(dbId);
            var added=GeometrySelection.All().Where(g=>!baseline.Contains(g.GetEntityID())).ToArray();
            if(added.Length!=1||added[0] is not SolidGeometry solid)throw new InvalidOperationException("独立实体复制数量回读失败。");
            solid.Level=source.Level;solid.Color=source.Color;if(!solid.Commit())throw new InvalidOperationException("副本属性写入失败。");return solid;
        }
        catch
        {
            foreach(var g in GeometrySelection.All().Where(g=>!baseline.Contains(g.GetEntityID())).ToArray())g.Delete();
            if(!transferred&&copy>0)Get<DeleteKernelDelegate>(kernel,"PK_ENTITY_delete")(1,ref copy);throw;
        }
        finally{Get<FreeTrackingDelegate>(kernel,"PK_ENTITY_track_r_f")(tracking);Marshal.FreeHGlobal(tracking);Marshal.FreeHGlobal(options);Marshal.FreeHGlobal(result);}
    }
}
