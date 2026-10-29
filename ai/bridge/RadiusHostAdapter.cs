using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using Mastercam.Database;
using Mastercam.Database.Types;
using Mastercam.IO;
using Mastercam.Support;
using Mastercam.Support.Types;
using MPDesignRadiusSelect2027.Core;
namespace MastercamPluginAI.RadiusAdapter;
public sealed class Api29Host:IRadiusHost
{
    readonly uint thread;static long epoch;
    internal static void ContextChanged()=>Interlocked.Increment(ref epoch);
    [DllImport("kernel32.dll")]static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")]static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
    public Api29Host()
    {
        using var p=Process.GetCurrentProcess();var w=Mastercam.UI.MastercamWindow.GetHandle();
        if(!p.ProcessName.Equals("Mastercam",StringComparison.OrdinalIgnoreCase)||w==null||w.Handle==IntPtr.Zero)throw new InvalidOperationException("需要Mastercam宿主UI线程。");
        thread=GetWindowThreadProcessId(w.Handle,out uint pid);if(pid!=Environment.ProcessId||thread!=GetCurrentThreadId())throw new InvalidOperationException("需要Mastercam宿主UI线程。");
    }
    void Check(){if(thread!=GetCurrentThreadId())throw new InvalidOperationException("禁止后台线程访问宿主。");}
    public static Geometry ReadEntity(int id){var g=Geometry.RetrieveEntity(id);if(g==null||!g.Retrieve()||g.GetEntityID()!=id)throw new InvalidOperationException("实体读取失败: "+id);return g;}
    string Context=>$"{Interlocked.Read(ref epoch)}|{SettingsManager.Metric}|{FileManager.CurrentFileName}";
    public Snapshot Capture()
    {
        Check();string context=Context;
        var alive=SearchManager.GetGeometry(new SelectionMask(true,false,false))??throw new InvalidOperationException("实体枚举失败。");
        var blanked=SearchManager.GetGeometry(new SelectionMask(false,false,true))??throw new InvalidOperationException("隐藏实体枚举失败。");
        var selected=SearchManager.GetSelectedGeometry()??throw new InvalidOperationException("选择枚举失败。");
        var all=alive.Concat(blanked).Concat(selected).Select(x=>x.GetEntityID()).Distinct().Order().ToArray();
        if(all.Length>100000)throw new InvalidOperationException("实体清单超过100000项。");
        var states=all.Select(id=>
        {
            var g=ReadEntity(id);
            string stamp=FormattableString.Invariant($"{g.GetType().FullName}|{g.TimeStamp:O}|{g.Level}|{g.Color}|{g.Blanked}|{g.LineStyle}|{g.LineWidth:R}|{g.PenStyle}");
            if(g is Mastercam.Curves.LineGeometry l)stamp+=FormattableString.Invariant($"|{l.EndPoint1.x:R},{l.EndPoint1.y:R},{l.EndPoint1.z:R}|{l.EndPoint2.x:R},{l.EndPoint2.y:R},{l.EndPoint2.z:R}");
            return new EntityState(id,g is SolidGeometry,!g.Blanked&&LevelsManager.IsLevelVisible(g.Level),g.Selected,stamp);
        }).ToArray();
        if(Context!=context)throw new InvalidOperationException("读取期间文档已变化。");
        var snapshot=new Snapshot(context,states);snapshot.Validate();return snapshot;
    }
    public void SetSelected(int id,bool selected)
    {
        Check();var g=ReadEntity(id);if(g.Selected==selected)return;
        var previous=PorscheAdvanced2027.GeometrySelection.Selected();var wanted=selected?previous.Append(id).Distinct().ToArray():previous.Where(i=>i!=id).ToArray();
        PorscheAdvanced2027.GeometrySelection.Set(wanted);if(ReadEntity(id).Selected!=selected)throw new InvalidOperationException("Selection readback failed");
    }
    public void Restore(Snapshot before)
    {
        Check();var now=Capture();Snapshot.SameGeometry(before,now);
        foreach(var e in before.Entities)if(now.Entities.Single(x=>x.Id==e.Id).Selected!=e.Selected)SetSelected(e.Id,e.Selected);
        Snapshot.Same(before,Capture());
    }
    static string AxisSeal(Axis2Managed a)=>FormattableString.Invariant($"{a.BodyLoc.x:R},{a.BodyLoc.y:R},{a.BodyLoc.z:R};{a.NormalVec.x:R},{a.NormalVec.y:R},{a.NormalVec.z:R};{a.RefAxis.x:R},{a.RefAxis.y:R},{a.RefAxis.z:R}");
    static string CirclesSeal(List<CircleAskResult>? circles)=>circles==null?"null":string.Join(";",circles.Select(c=>AxisSeal(c.Axis)+"/"+c.Radius.ToString("R",System.Globalization.CultureInfo.InvariantCulture)).Order(StringComparer.Ordinal));
    public FaceInfo[] ReadFaces(int[] ids)
    {
        Check();if(ids.Length is <1 or >128||ids.Distinct().Count()!=ids.Length)throw new ArgumentException("实体范围无效。");
        var baseline=Capture();var output=new List<FaceInfo>();
        foreach(int id in ids)
        {
            if(!baseline.Entities.Any(e=>e.Id==id&&e.Solid&&e.Visible))throw new InvalidOperationException("范围内实体不可见或无效: "+id);
            Exception? error=null;
            try
            {
                // API29 0x06002411 clears selection. This query must always be paired with exact restoration.
                var map=SearchManager.GetFaceTagsAndPidMapFromBodyEntity(id);
                if(map==null||map.Count<1||output.Count+map.Count>4096||map.Keys.Any(k=>k<=0)||map.Values.Any(v=>v<=0)||map.Values.Distinct().Count()!=map.Count)throw new InvalidOperationException("实体面枚举无效或超过4096面: "+id);
                bool metric=SettingsManager.Metric;
                foreach(var pair in map.OrderBy(x=>x.Key))
                {
                    if(SearchManager.GetPersistentIDFromFaceTag(pair.Value)!=pair.Key)throw new InvalidOperationException("面标识读回不一致。");
                    var p=SearchManager.GetFaceTypeAndParameters(pair.Value);
                    if(p==null||p.ResultType is not ResultType kind)throw new InvalidOperationException("解析面查询失败。");
                    double? radius=null,major=null;string seal=kind.ToString();
                    switch(kind)
                    {
                        case ResultType.Cylinder:if(p.Cylinder==null)throw new InvalidOperationException("圆柱参数缺失。");radius=RadiusUnits.ToModel(p.Cylinder.Radius,metric);seal+=AxisSeal(p.Cylinder.Axis)+CirclesSeal(p.Cylinder.EdgeCircles);break;
                        case ResultType.Sphere:if(p.Sphere==null)throw new InvalidOperationException("球面参数缺失。");radius=RadiusUnits.ToModel(p.Sphere.Radius,metric);seal+=AxisSeal(p.Sphere.Axis)+CirclesSeal(p.Sphere.EdgeCircles);break;
                        case ResultType.Torus:if(p.Torus==null)throw new InvalidOperationException("环面参数缺失。");radius=RadiusUnits.ToModel(p.Torus.MinRadius,metric);major=RadiusUnits.ToModel(p.Torus.MajRadius,metric);seal+=AxisSeal(p.Torus.Axis)+CirclesSeal(p.Torus.EdgeCircles);break;
                        case ResultType.Cone:if(p.Cone==null)throw new InvalidOperationException("锥面参数缺失。");radius=RadiusUnits.ToModel(p.Cone.Radius,metric);seal+=AxisSeal(p.Cone.Axis)+CirclesSeal(p.Cone.EdgeCircles)+p.Cone.SemiAngle.ToString("R",System.Globalization.CultureInfo.InvariantCulture);break;
                    }
                    if(radius is double r&&(!double.IsFinite(r)||r<0||(r==0&&kind!=ResultType.Cone))||major is double m&&(!double.IsFinite(m)||m<=0))throw new InvalidOperationException("解析半径无效。");
                    // Managed values only. No transient tag retained in the session or across UI events.
                    output.Add(new(id,pair.Key,kind.ToString(),radius,major,seal));
                }
            }
            catch(Exception ex){error=ex;}
            try{Restore(baseline);}catch(Exception recovery){throw new AggregateException("解析查询的选择恢复未能确认。",error==null?new[]{recovery}:new[]{error,recovery});}
            if(error!=null)System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(error).Throw();
        }
        Snapshot.Same(baseline,Capture());return output.ToArray();
    }
}
public static class RadiusTools
{
    static int busy;
    public static void Run(Action<RadiusSession> action)
    {
        if(Interlocked.CompareExchange(ref busy,1,0)!=0)throw new InvalidOperationException("半径选择正在运行。");
        try{using var session=new RadiusSession(new Api29Host());action(session);}finally{Interlocked.Exchange(ref busy,0);}
    }
}
