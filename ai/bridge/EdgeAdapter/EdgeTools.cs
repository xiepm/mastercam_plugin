using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Support;
[assembly:InternalsVisibleTo("MastercamPluginAI.EdgeAdapter.NativeChecks")]
namespace MastercamPluginAI.EdgeAdapter;

public sealed record EdgePreview(EdgeRequest Request,EdgeGeometry Geometry,string SourceSeal,string Signature);
public sealed record EdgeReceipt(EdgePreview Preview,int[] GeometryIds,bool Committed,string Contract);
public static class EdgeTools
{
    public const string Contract="单个可见选中实体；闭合平面面、直线边；真实3D全边或世界XY正投影；仅已有可见输出层；不做隐藏线消除/轮廓推断/部分重叠合并。";
    static int busy;
    [DllImport("user32.dll")]static extern uint GetWindowThreadProcessId(IntPtr h,out uint process);
    [DllImport("kernel32.dll")]static extern uint GetCurrentThreadId();
    internal static void RequireThread()
    {
        uint thread=GetWindowThreadProcessId(Mastercam.UI.MastercamWindow.GetHandle().Handle,out uint pid);
        BoundaryKernel.Require(Thread.CurrentThread.GetApartmentState()==ApartmentState.STA&&thread==GetCurrentThreadId()&&pid==Environment.ProcessId,"须在Mastercam主窗口STA线程同步调用。");
        BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"已有事务，拒绝加入或取消调用者事务。");
    }
    public static int[] GetExistingVisibleOutputLevels(){RequireThread();return OutputLevelAdmission.Eligible(NativeBoundary.ContextSeal());}
    public static EdgePreview Preview(EdgeRequest request)=>Run(request,null,false,null).Preview;
    public static EdgeReceipt Create(EdgeRequest request,string expectedPreviewSignature)=>Run(request,expectedPreviewSignature,true,null);
    public static AuditStep[] LastAudit=>NativeBoundary.LastAudit;
    internal static EdgeReceipt Run(EdgeRequest request,string signature,bool commit,Action<string> fault)
    {
        RequireThread();BoundaryKernel.Require(Interlocked.CompareExchange(ref busy,1,0)==0,"边工具正在运行。");
        try{return NativeBoundary.ExecuteEdges(request,signature,commit,fault);}finally{Volatile.Write(ref busy,0);}
    }
}
internal static class ExtractionDiagnostics
{
    internal static int[] SelectedIds()=>SearchManager.GetSelectedGeometry().Select(g=>g.GetEntityID()).Order().ToArray();
}
public static partial class NativeBoundary
{
    internal static EdgeReceipt ExecuteEdges(EdgeRequest r,string expected,bool commit,Action<string> fault)
    {
        ClearAudit();BoundaryKernel.Require(r!=null&&r.SourceId>0&&r.Color>=0&&r.Color<=255,"无效源实体或颜色。");
        BoundaryKernel.Require(!commit||!string.IsNullOrEmpty(expected),"先预览并传入该预览签名。");
        RequireWorldXY(ViewManager.CPlane);
        string context=ContextSeal();OutputLevelAdmission.RequireExistingVisible(context,r.OutputLevel);
        var selectedBefore=ExtractionDiagnostics.SelectedIds();var baseline=Capture();var document=NativeDocumentInventory.Capture();
        BoundaryKernel.Require(selectedBefore.SequenceEqual(new[]{r.SourceId})&&selectedBefore.SequenceEqual(ExtractionDiagnostics.SelectedIds()),"请仅预选一个实体；拒绝混选或采样期间选择变化。");
        var source=Geometry.RetrieveEntity(r.SourceId);
        BoundaryKernel.Require(source is SolidGeometry&&source.Retrieve()&&!source.Blanked&&LevelsManager.IsLevelVisible(source.Level),"只支持可见实体模型；曲面、线框和隐藏实体不支持。");
        var faces=ReadFaces(r.SourceId);string faceSeal=JsonSerializer.Serialize(faces);
        var geometry=RolledBack(baseline,()=>
        {
            fault?.Invoke("before-extraction");var edges=NativeSolidEdges.Read(faces,r.Tolerance,fault);
            VerifyExisting(baseline);VerifyIds(baseline.Keys);VerifyContext(context);NativeDocumentInventory.Verify(document,"after-public-edge-read");
            fault?.Invoke("after-extraction");return EdgeKernel.Plan(edges,r.Mode,r.OutputZ,r.Tolerance);
        });
        BoundaryKernel.Require(JsonSerializer.Serialize(ReadFaces(r.SourceId))==faceSeal,"预览期间源实体拓扑改变。");
        VerifyExisting(baseline);VerifyIds(baseline.Keys);VerifyContext(context);NativeDocumentInventory.Verify(document,"after-preview");
        string seal=JsonSerializer.Serialize(new{faces,source=baseline[r.SourceId]});
        string signature=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new{request=r,geometry,seal}))));
        var preview=new EdgePreview(r,geometry,seal,signature);
        Record("edge-preview-verified",new{mode=r.Mode.ToString(),sourceEdges=geometry.SourceEdges.Length,outputLines=geometry.Segments.Length,geometry.CollapsedTags,geometry.MergedDuplicates,signature},verified:true);
        if(!commit)return new(preview,Array.Empty<int>(),false,EdgeTools.Contract);
        BoundaryKernel.Require(signature==expected,"参数、源实体或预选状态与预览不一致；请重新预览。");
        OutputLevelAdmission.RequireExistingVisible(ContextSeal(),r.OutputLevel);
        var level=new NativeOutputLevelLease(r.OutputLevel,context);bool owns=false;var ids=new List<int>();
        try
        {
            BoundaryKernel.Require(UndoManager.StartTransaction(),"无法开始边输出事务。");owns=true;
            foreach(var segment in geometry.Segments)
            {
                var line=new LineGeometry(P(segment.A),P(segment.B)){Level=r.OutputLevel,Color=(byte)r.Color,Selected=false,Blanked=false};
                bool created=false;try{created=line.Commit();}finally{int id=line.GetEntityID();if(id>0&&!baseline.ContainsKey(id))ids.Add(id);}
                BoundaryKernel.Require(created&&ids.Count>0,"输出直线Commit失败。");
                var fresh=Geometry.RetrieveEntity(ids[^1]);BoundaryKernel.Require(fresh is LineGeometry&&fresh.Retrieve(),"输出直线即时读回失败。");
                fresh.Level=r.OutputLevel;fresh.Color=(byte)r.Color;fresh.Selected=false;fresh.Blanked=false;
                BoundaryKernel.Require(fresh.Commit(),"输出属性Commit失败。");VerifyLine(ids[^1],segment,r);
                fault?.Invoke("after-output-line");
            }
            BoundaryKernel.Require(ids.Count==geometry.Segments.Length&&ids.Distinct().Count()==ids.Count,"输出ID集合不完整。");
            RestoreSelection(baseline);VerifyExisting(baseline);VerifyIds(baseline.Keys.Concat(ids));
            BoundaryKernel.Require(JsonSerializer.Serialize(ReadFaces(r.SourceId))==faceSeal,"源实体拓扑改变。");
            for(int i=0;i<ids.Count;i++)VerifyLine(ids[i],geometry.Segments[i],r);
            level.PrepareCommit();NativeDocumentInventory.Verify(document,"before-output-commit");
            fault?.Invoke("before-output-commit");UndoManager.CommitTransaction();
            BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"输出提交后事务仍活动。");owns=false;
            Record("edge-output-committed",new{ids=ids.ToArray(),mode=r.Mode.ToString(),outputLevel=r.OutputLevel},ids.ToArray(),true);
            return new(preview,ids.ToArray(),true,EdgeTools.Contract);
        }
        catch(Exception original)
        {
            if(owns)
            {
                try{CancelAndVerify(baseline,context,ids,level,()=>NativeDocumentInventory.Verify(document,"after-output-rollback"));}
                catch(Exception recovery){throw new AggregateException("边输出失败且恢复未完全确认，请人工复核。",original,recovery);}
            }
            throw;
        }
    }
    internal static void VerifyLine(int id,OutputSegment expected,EdgeRequest r)
    {
        var g=Geometry.RetrieveEntity(id);BoundaryKernel.Require(g is LineGeometry&&g.Retrieve(),"输出直线不存在："+id);
        var line=(LineGeometry)g;
        BoundaryKernel.Require((V(line.EndPoint1)-expected.A).Length<=r.Tolerance&&(V(line.EndPoint2)-expected.B).Length<=r.Tolerance&&line.Level==r.OutputLevel&&line.Color==r.Color&&!line.Selected&&!line.Blanked,"输出坐标/图层/颜色/选择/隐藏状态读回不符："+id);
    }
}
