using System;
using System.Collections.Generic;
using System.Linq;
using Mastercam.BasicGeometry;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.Database.Types;
using Mastercam.GeometryUtility;
using Mastercam.GeometryUtility.Types;
using Mastercam.IO;
using Mastercam.Math;
using Mastercam.Support;
using Mastercam.Support.Types;

namespace MastercamPluginAI.GeometryAdapter;

public enum GeometryCommand { CenterXY, CenterXYZ, RotateX90, RotateY90, RotateZ90, AlignCplane, PaintZPlanes, PaintVerticalPlanes, DimensionBounds, MergeCurves, ChamferEdges, AssignLevel }
public sealed class GeometryRequest
{
    public GeometryCommand Command {get;set;}
    public V3 Destination {get;set;}
    public int QuarterTurns {get;set;}=1;
    public int Color {get;set;}=10;
    public int Level {get;set;}=1;
    public double AngleTolerance {get;set;}=0.01;
    public double CurveTolerance {get;set;}=0.01;
    public double ChamferDistance {get;set;}=1;
    public double TextHeight {get;set;}=2.5;
    public double DimensionOffset {get;set;}=5;
    public int Decimals {get;set;}=3;
    public int[] EdgeTags {get;set;}=Array.Empty<int>();
    internal GeometryRequest Copy()=>new(){Command=Command,Destination=Destination,QuarterTurns=QuarterTurns,Color=Color,Level=Level,AngleTolerance=AngleTolerance,CurveTolerance=CurveTolerance,ChamferDistance=ChamferDistance,TextHeight=TextHeight,DimensionOffset=DimensionOffset,Decimals=Decimals,EdgeTags=(int[])EdgeTags.Clone()};
}
public sealed class GeometryPlan
{
    public int[] EntityIds=> (int[])Ids.Clone();
    public Bounds3 Before {get;internal set;}
    public string Description {get;internal set;}="";
    internal int[] Ids=Array.Empty<int>();
    internal GeometryRequest Request;
    internal EntityState[] Original;
    internal FaceState[] Faces=Array.Empty<FaceState>();
    internal string[] EdgeIdentities=Array.Empty<string>();
    internal Frame3 SourceFrame;
    internal short SourceView;
    internal string File="";
    internal bool Used;
}
internal sealed record FaceState(int Body,int Pid,int Tag,string Type,V3 Normal,byte Color,string ColorSource);
internal sealed record EntityState(int Id,string Type,int Level,int Color,bool Selected,bool Blanked,DateTime Stamp,V3[] Points,FaceState[] Faces)
{
    internal bool Equivalent(EntityState b,bool stamp=false,bool attributes=true)
    {
        if(Id!=b.Id||Type!=b.Type||(attributes&&(Level!=b.Level||Color!=b.Color||Selected!=b.Selected||Blanked!=b.Blanked))||(stamp&&Stamp!=b.Stamp)||Points.Length!=b.Points.Length||Faces.Length!=b.Faces.Length)return false;
        if(!Points.Zip(b.Points).All(p=>p.First.Near(p.Second,1e-7)))return false;
        return Faces.Zip(b.Faces).All(p=>p.First.Pid==p.Second.Pid&&p.First.Type==p.Second.Type&&p.First.Normal.Near(p.Second.Normal,1e-7)&&(!attributes||(p.First.Color==p.Second.Color&&p.First.ColorSource==p.Second.ColorSource)));
    }
}
internal sealed class NativeTransaction : IEditTransaction
{
    public bool Active=>UndoManager.IsTransactionActive();
    public bool Begin()=>UndoManager.StartTransaction();
    public void Commit()=>UndoManager.CommitTransaction();
    public void Cancel()=>UndoManager.CancelTransaction();
}
internal sealed class ViewState
{
    readonly MCView wcs=ViewManager.WorkCoordinateSystem,cp=ViewManager.CPlane,tp=ViewManager.TPlane,gp=ViewManager.GraphicsView;
    readonly bool cf=ViewManager.CplaneFollowsWcs,gf=ViewManager.GplaneFollowsWcs,cg=ViewManager.CplaneFollowsGplane,ci=ViewManager.CplaneTopWhenGplaneIso,c3=SettingsManager.ConstructionView3D;
    readonly double depth=ViewManager.ConstructionDepth;
    internal static void Detach(){ViewManager.CplaneFollowsWcs=false;ViewManager.GplaneFollowsWcs=false;ViewManager.CplaneFollowsGplane=false;ViewManager.CplaneTopWhenGplaneIso=false;}
    internal static void Use(MCView frame){Detach();ViewManager.WorkCoordinateSystem=frame;ViewManager.GraphicsView=frame;ViewManager.CPlane=frame;ViewManager.TPlane=frame;SettingsManager.ConstructionView3D=true;}
    internal void Restore()
    {
        Detach();ViewManager.WorkCoordinateSystem=wcs;ViewManager.GraphicsView=gp;ViewManager.CPlane=cp;ViewManager.TPlane=tp;ViewManager.ConstructionDepth=depth;SettingsManager.ConstructionView3D=c3;
        ViewManager.CplaneTopWhenGplaneIso=ci;ViewManager.CplaneFollowsGplane=cg;ViewManager.GplaneFollowsWcs=gf;ViewManager.CplaneFollowsWcs=cf;
        if(ViewManager.WorkCoordinateSystem.ViewID!=wcs.ViewID||ViewManager.CPlane.ViewID!=cp.ViewID||ViewManager.TPlane.ViewID!=tp.ViewID||ViewManager.GraphicsView.ViewID!=gp.ViewID||ViewManager.ConstructionDepth!=depth||SettingsManager.ConstructionView3D!=c3||ViewManager.CplaneTopWhenGplaneIso!=ci||ViewManager.CplaneFollowsGplane!=cg||ViewManager.GplaneFollowsWcs!=gf||ViewManager.CplaneFollowsWcs!=cf)throw new InvalidOperationException("坐标/视图设置恢复回读失败");
    }
}
public static class HostGeometry
{
    internal static V3 V(Point3D p)=>new(p.x,p.y,p.z);
    internal static Point3D P(V3 p)=>new(p.X,p.Y,p.Z);
    internal static Frame3 Frame(MCView view){var m=view.ViewMatrix;var f=new Frame3(V(view.ViewOrigin),V(m.Row1),V(m.Row2),V(m.Row3));f.Validate();return f;}
    internal static MCView World()=> (ViewManager.GetAllViews(false)??Array.Empty<MCView>()).FirstOrDefault(v=>{var f=Frame(v);return f.Origin.Near(new(),1e-10)&&f.X.Near(new(1,0,0),1e-10)&&f.Y.Near(new(0,1,0),1e-10)&&f.Z.Near(new(0,0,1),1e-10);})??throw new InvalidOperationException("找不到世界 XY 坐标视图");
    internal static Geometry[] All()=> (SearchManager.GetGeometry(new GeometryMask(true),new SelectionMask(true,false,false),-1)??Array.Empty<Geometry>()).Concat(SearchManager.GetGeometry(new GeometryMask(true),new SelectionMask(true,false,true),-1)??Array.Empty<Geometry>()).GroupBy(g=>g.GetEntityID()).Select(g=>g.First()).ToArray();
    public static int[] CurrentSelection()=>All().Where(g=>g.Selected).Select(g=>g.GetEntityID()).OrderBy(i=>i).ToArray();
    internal static Geometry Get(int id){var g=Geometry.RetrieveEntity(id);if(g==null||!g.Retrieve()||g.GetEntityID()!=id)throw new InvalidOperationException("图素失效："+id);return g;}
    internal static int[] Scope(int[] ids)
    {
        if(ids==null||ids.Length==0||ids.Length>5000||ids.Any(id=>id<=0)||ids.Distinct().Count()!=ids.Length)throw new ArgumentException("请明确选择 1–5000 个不同图素");
        var sorted=ids.OrderBy(i=>i).ToArray();
        if(!sorted.SequenceEqual(CurrentSelection()))throw new InvalidOperationException("ID 必须恰好等于当前完整选择；选择已变化");
        foreach(int id in sorted){var g=Get(id);if(!g.Validate()||!LevelsManager.IsLevelVisible(g.Level))throw new InvalidOperationException("图素无效或所在图层未显示："+id);}
        return sorted;
    }
    internal static FaceState[] Faces(int body)
    {
        using var selection=new PorscheAdvanced2027.GeometrySelection();
        var map=SearchManager.GetFaceTagsAndPidMapFromBodyEntity(body);
        if(map==null||map.Count==0)throw new InvalidOperationException("实体面映射为空："+body);
        return map.OrderBy(p=>p.Key).Select(p=>{
            var type=SearchManager.GetFaceTypeAndParameters(p.Value)?.ResultType?.ToString()??"Unknown";
            var normal=V(SearchManager.GetFaceNormal(p.Value));
            byte color;var source=Colors.GetFaceColor(p.Value,out color);
            if(source==Colors.FaceColorResult.InvalidTag)throw new InvalidOperationException("实体面颜色读取失败");
            return new FaceState(body,p.Key,p.Value,type,normal,color,source.ToString());
        }).ToArray();
    }
    internal static Dictionary<int,int[]> FaceEdges(FaceState[] faces)=>faces.ToDictionary(f=>f.Pid,f=>SearchManager.GetEdgeTagsFromFace(f.Tag)??Array.Empty<int>());
    internal static EntityState State(Geometry g,bool solidDetail)
    {
        var points=g is PointGeometry point?new[]{V(point.Data)}:g is CurveGeometry curve?new[]{V(curve.EndPoint1),V(curve.EndPoint2)}:Array.Empty<V3>();
        return new(g.GetEntityID(),g.GetType().FullName??"",g.Level,g.Color,g.Selected,g.Blanked,g.TimeStamp,points,solidDetail&&g is SolidGeometry?Faces(g.GetEntityID()):Array.Empty<FaceState>());
    }
    internal static EntityState[] States(int[] ids)=>ids.Select(id=>State(Get(id),true)).ToArray();
    internal static void SameStates(EntityState[] expected)
    {
        foreach(var a in expected)if(!a.Equivalent(State(Get(a.Id),true)))throw new InvalidOperationException("图素状态回读不符："+a.Id);
    }
    internal static void RestoreFlags(EntityState[] before)
    {
        foreach(var a in before)if(Get(a.Id).Blanked!=a.Blanked)throw new InvalidOperationException("Unexpected blanked change; inspect before recovery.");
        var scoped=before.Select(x=>x.Id).ToHashSet();
        var wanted=PorscheAdvanced2027.GeometrySelection.Selected().Where(id=>!scoped.Contains(id)).Concat(before.Where(x=>x.Selected).Select(x=>x.Id)).ToArray();
        PorscheAdvanced2027.GeometrySelection.Set(wanted);
    }
    internal static void OutsideUnchanged(Dictionary<int,EntityState> before,int[] scope,IEnumerable<int> created)
    {
        var allowed=scope.ToHashSet();var owned=created.ToHashSet();var after=All();
        if(!before.Keys.Concat(owned).OrderBy(i=>i).SequenceEqual(after.Select(g=>g.GetEntityID()).OrderBy(i=>i)))throw new InvalidOperationException("图素 ID 集合超出计划");
        foreach(var g in after)if(before.TryGetValue(g.GetEntityID(),out var old)&&!allowed.Contains(g.GetEntityID())&&!old.Equivalent(State(g,false),true))throw new InvalidOperationException("检测到未选图素变化："+g.GetEntityID());
    }
    /// <summary>Host UI thread only. Requires ids to be exactly the complete current selection.
    /// Rejects an existing transaction. Returns world bounds; temporary copies and corners are deleted; source timestamps are checked.</summary>
    public static Bounds3 MeasureSelected(int[] entityIds)
    {
        var ids=Scope(entityIds);
        return Measure(ids,World());
    }
    internal static Bounds3 Measure(int[] ids,MCView frame)
    {
        if(ids.Length==0)throw new ArgumentException("空范围");var basis=Frame(frame);
        var input=ids.Select(Get).ToArray();
        if(input.All(g=>g is PointGeometry||g is LineGeometry))return Bounds3.Of(input.SelectMany(g=>g is PointGeometry p?new[]{V(p.Data)}:new[]{V(((LineGeometry)g).EndPoint1),V(((LineGeometry)g).EndPoint2)}).Select(basis.ToLocal));
        var scene=All().ToDictionary(g=>g.GetEntityID(),g=>State(g,false));
        var scope=scene.Values.Where(s=>s.Selected).ToArray();
        if(ids.Any(id=>!scene.ContainsKey(id)||!scene[id].Selected)||!ids.OrderBy(i=>i).SequenceEqual(scope.Select(s=>s.Id).OrderBy(i=>i)))throw new InvalidOperationException("原生测量需要完整选择范围");
        var state=new ViewState();bool own=!UndoManager.IsTransactionActive();var temporary=new List<int>();Bounds3 result=null;
        if(own&&!UndoManager.StartTransaction())throw new InvalidOperationException("无法开始测量事务");
        var errors=new List<Exception>();
        try{
            ViewState.Use(frame);
            PorscheAdvanced2027.GeometrySelection.Set(Array.Empty<int>());
            // API29 RectangularBoundingBox commits its input entities. Measure owned copies only.
            var world=World();var copies=new List<Geometry>();
            foreach(int id in ids){var copy=Get(id) is SolidGeometry?SolidCopyAdapter.CopyIndependent(id):Get(id).CopyAndTranslate(new Point3D(),new Point3D(),world,world);int fresh=copy?.GetEntityID()??0;
                if(fresh<=0||scene.ContainsKey(fresh)||temporary.Contains(fresh))throw new InvalidOperationException("Invalid measurement copy ID");temporary.Add(fresh);copies.Add(Get(fresh));}
            PorscheAdvanced2027.GeometrySelection.Set(Array.Empty<int>());
            Point3D low,high;
            var output=GeometryCreationManager.RectangularBoundingBox(new BoundingBoxCommonParams{CreatePoints=true,CreateLinesArcs=false,CreateCenterPoint=false,CreateSolid=false},new BoundingBoxRectangularParams(),copies.ToArray(),out low,out high);
            if(output==null||output.Length==0||output.Length>8)throw new InvalidOperationException("原生包围盒没有有效角点");
            var cornerIds=new List<int>();foreach(var g in output){int fresh=g?.GetEntityID()??0;if(fresh<=0||scene.ContainsKey(fresh)||temporary.Contains(fresh))throw new InvalidOperationException("非法临时角点 ID");temporary.Add(fresh);cornerIds.Add(fresh);}
            result=Bounds3.Of(cornerIds.Select(id=>basis.ToLocal(V((Get(id) as PointGeometry??throw new InvalidOperationException("角点类型不符")).Data))));result.Validate();
        }catch(Exception e){errors.Add(e);}
        foreach(int id in temporary.AsEnumerable().Reverse())try{var g=Geometry.RetrieveEntity(id);if(g!=null&&!g.Delete(false))throw new InvalidOperationException("Temporary geometry delete failed: "+id);}catch(Exception e){errors.Add(e);}
        try{RestoreFlags(scope);state.Restore();if(own){if(!UndoManager.IsTransactionActive())throw new InvalidOperationException("Measurement transaction unexpectedly ended");UndoManager.CommitTransaction();}}
        catch(Exception e){errors.Add(e);}
        try{OutsideUnchanged(scene,Array.Empty<int>(),Array.Empty<int>());}catch(Exception e){errors.Add(e);}
        if(errors.Count>0)throw new AggregateException("包围盒测量失败："+string.Join("；",errors.Select(e=>e.Message)),errors);
        return result;
    }
    public static GeometryPlan Prepare(int[] entityIds,GeometryRequest request)
    {
        if(request==null||request.EdgeTags==null||!Enum.IsDefined(request.Command))throw new ArgumentException("无效请求");
        if(UndoManager.IsTransactionActive())throw new InvalidOperationException("宿主已有事务");
        var ids=Scope(entityIds);var r=request.Copy();
        if(r.Color<0||r.Color>255||r.Level<1||r.QuarterTurns==0||Math.Abs((long)r.QuarterTurns)>4||!r.Destination.Finite||!double.IsFinite(r.ChamferDistance)||r.ChamferDistance<=0||!double.IsFinite(r.CurveTolerance)||r.CurveTolerance<=0||r.CurveTolerance>1)throw new ArgumentException("参数超出范围");
        var original=States(ids);var world=World();var cp=ViewManager.CPlane;var plan=new GeometryPlan{Ids=ids,Request=r,Original=original,File=FileManager.CurrentFileName??"",SourceFrame=Frame(cp),SourceView=cp.ViewID};
        // Capture edge identity BEFORE Measure can cancel a temporary transaction and rebuild tags.
        if(r.Command==GeometryCommand.ChamferEdges){
            if(ids.Length!=1||Get(ids[0]) is not SolidGeometry||r.EdgeTags.Length==0||r.EdgeTags.Distinct().Count()!=r.EdgeTags.Length)throw new ArgumentException("倒角需要一个选定实体和明确选择的边");
            var topology=FaceEdges(original[0].Faces);
            plan.EdgeIdentities=r.EdgeTags.Select(e=>EdgeTopology.Capture(e,topology)).ToArray();
        }
        plan.Before=Measure(ids,world);SameStates(original);
        if(r.Command==GeometryCommand.PaintZPlanes||r.Command==GeometryCommand.PaintVerticalPlanes){
            if(ids.Any(id=>Get(id) is not SolidGeometry))throw new ArgumentException("着色仅接受选定实体；不推断曲面中点代表整个面");
            plan.Faces=original.SelectMany(s=>s.Faces).Where(f=>GeometryMath.IsPlanarDirection(f.Type==ResultType.Plane.ToString(),f.Normal,r.Command==GeometryCommand.PaintZPlanes,r.AngleTolerance)).ToArray();
            if(plan.Faces.Length==0)throw new InvalidOperationException("没有符合角容差的平面");
        }
        if(r.Command==GeometryCommand.MergeCurves){
            if(ids.Any(id=>Get(id) is not CurveGeometry))throw new ArgumentException("合并仅接受曲线");
            GeometryMath.OrderSimpleChain(ids.Select(id=>(CurveGeometry)Get(id)).Select(c=>(V(c.EndPoint1),V(c.EndPoint2))).ToArray(),r.CurveTolerance);
        }
        if(r.Command==GeometryCommand.DimensionBounds)_=DimensionWireframe.Create(plan.Before,r.TextHeight,r.DimensionOffset,r.Decimals);
        if(r.Command==GeometryCommand.ChamferEdges){
            var currentTopology=FaceEdges(Faces(ids[0]));
            foreach(string identity in plan.EdgeIdentities)_=EdgeTopology.Resolve(identity,currentTopology);
        }
        if(r.Command==GeometryCommand.AlignCplane){_ = Frame(cp);plan.Before=Measure(ids,cp);SameStates(original);}
        if(r.Command is GeometryCommand.AssignLevel or GeometryCommand.DimensionBounds or GeometryCommand.MergeCurves){if(!LevelsManager.IsLevelVisible(r.Level))throw new InvalidOperationException("目标层必须已存在并显示");}
        plan.Description=$"操作：{r.Command}\r\n明确选中图素：{ids.Length}\r\n范围：{plan.Before.Min} → {plan.Before.Max}\r\n平面候选：{plan.Faces.Length}；边：{r.EdgeTags.Length}\r\n";
        if(r.Command==GeometryCommand.DimensionBounds)plan.Description+="创建非关联线框尺寸，不修改来源图素。\r\n";
        if(r.Command==GeometryCommand.MergeCurves)plan.Description+="创建一个 NURBS，保留原曲线；偏差上限 "+r.CurveTolerance+" 文档单位。\r\n";
        if(r.Command==GeometryCommand.ChamferEdges)plan.Description+="仅给定边等距倒角；不扩展相切链。\r\n";
        return plan;
    }
    public static int[] Execute(GeometryPlan plan)
    {
        if(plan==null||plan.Used)throw new InvalidOperationException("请重新预检");
        Scope(plan.Ids);if((FileManager.CurrentFileName??"")!=plan.File)throw new InvalidOperationException("文档已变化");
        SameStates(plan.Original);var r=plan.Request;var world=World();var cp=ViewManager.CPlane;
        if(r.Command==GeometryCommand.AlignCplane&&(cp.ViewID!=plan.SourceView||Frame(cp)!=plan.SourceFrame))throw new InvalidOperationException("构图平面已变化");
        var now=Measure(plan.Ids,r.Command==GeometryCommand.AlignCplane?cp:world);if(!now.Near(plan.Before,1e-7))throw new InvalidOperationException("几何在预检后改变");
        var scene=All().ToDictionary(g=>g.GetEntityID(),g=>State(g,false));var context=new ViewState();var created=new List<int>();Bounds3 expected=plan.Before;plan.Used=true;
        void Add(Geometry g){if(g==null||!g.Commit()||g.GetEntityID()<=0||scene.ContainsKey(g.GetEntityID())||created.Contains(g.GetEntityID()))throw new InvalidOperationException("新图素创建失败或 ID 冲突");created.Add(g.GetEntityID());if(!Get(g.GetEntityID()).Validate())throw new InvalidOperationException("新图素校验失败");}
        AtomicEdit.Run(new NativeTransaction(),()=>{
            ViewState.Use(world);
            switch(r.Command){
            case GeometryCommand.PaintZPlanes:
            case GeometryCommand.PaintVerticalPlanes:
                foreach(var f in plan.Faces){var current=Faces(f.Body).Single(x=>x.Pid==f.Pid);int tag=SearchManager.GetFaceTagsFromBodyEntityAndPid(f.Body,f.Pid);if(tag<=0||tag!=current.Tag)throw new InvalidOperationException("当前面 PID/tag 映射不一致");if(current.Type!=f.Type||!current.Normal.Near(f.Normal,1e-7))throw new InvalidOperationException("面定义已改变");if(!Colors.SetFaceColor(tag,(byte)r.Color))throw new InvalidOperationException("面着色失败");}
                break;
            case GeometryCommand.CenterXY:
            case GeometryCommand.CenterXYZ:
                var delta=GeometryMath.CenterDelta(plan.Before,r.Destination,r.Command==GeometryCommand.CenterXYZ);expected=new(plan.Before.Min+delta,plan.Before.Max+delta);
                foreach(int id in plan.Ids){var g=Get(id);if(!g.Translate(new Point3D(),P(delta),world,world)||!g.Commit())throw new InvalidOperationException("平移失败："+id);}
                break;
            case GeometryCommand.RotateX90:
            case GeometryCommand.RotateY90:
            case GeometryCommand.RotateZ90:
                var axis=r.Command==GeometryCommand.RotateX90?new V3(1,0,0):r.Command==GeometryCommand.RotateY90?new V3(0,1,0):new V3(0,0,1);
                var rotationView=(ViewManager.GetAllViews(false)??Array.Empty<MCView>()).FirstOrDefault(v=>Frame(v).Z.Near(axis,1e-8))??throw new InvalidOperationException("缺少旋转轴对应的标准视图");
                var pivot=plan.Before.Center;double degrees=r.QuarterTurns*90;
                expected=Bounds3.Of(Corners(plan.Before).Select(p=>GeometryMath.Rotate(p,pivot,axis,degrees)));
                foreach(int id in plan.Ids){var g=Get(id);if(!g.Rotate(P(pivot),degrees,rotationView)||!g.Commit())throw new InvalidOperationException("旋转失败："+id);}
                break;
            case GeometryCommand.AlignCplane:
                foreach(int id in plan.Ids){var g=Get(id);if(!g.Translate(P(plan.SourceFrame.Origin),new Point3D(),cp,world)||!g.Commit())throw new InvalidOperationException("坐标对齐失败："+id);}
                break;
            case GeometryCommand.DimensionBounds:
                foreach(var s in DimensionWireframe.Create(plan.Before,r.TextHeight,r.DimensionOffset,r.Decimals))Add(new LineGeometry(P(s.A),P(s.B)){Color=r.Color,Level=r.Level,Selected=false});
                break;
            case GeometryCommand.MergeCurves:
                var chains=ChainManager.ChainGeometry(plan.Ids.Select(Get).ToArray());
                if(chains==null||chains.Length!=1)throw new InvalidOperationException("宿主未形成唯一串连");
                var chainIds=(ChainManager.GetGeometryInChain(chains[0])??Array.Empty<CurveGeometry>()).Select(g=>g.GetEntityID()).OrderBy(i=>i).ToArray();
                if(!chainIds.SequenceEqual(plan.Ids))throw new InvalidOperationException("串连范围与所选图素不符");
                var spline=GeometryCreationManager.CreateNURBSSplineFromChain(chains[0],r.CurveTolerance,OriginalCurvesDisposition.Keep,r.Level);
                if(spline==null||spline.GetEntityID()<=0||scene.ContainsKey(spline.GetEntityID()))throw new InvalidOperationException("NURBS 创建失败");
                created.Add(spline.GetEntityID());spline=Get(spline.GetEntityID()) as NURBSCurveGeometry??throw new InvalidOperationException("结果非 NURBS");
                spline.Color=r.Color;spline.Level=r.Level;spline.Selected=false;if(!spline.Commit())throw new InvalidOperationException("NURBS 属性提交失败");
                spline=Get(spline.GetEntityID()) as NURBSCurveGeometry??throw new InvalidOperationException("NURBS 回读类型错误");
                if(!double.IsFinite(spline.Length)||spline.Length<=0||!spline.Validate()||spline.ControlPoints.Any(p=>!V(p).Finite))throw new InvalidOperationException("NURBS 回读失败");
                if(Math.Abs(spline.Length-chains[0].Perimeter)>r.CurveTolerance*4*plan.Ids.Length)throw new InvalidOperationException("NURBS 长度与原串连差异过大");
                break;
            case GeometryCommand.ChamferEdges:
                var solid=(SolidGeometry)Get(plan.Ids[0]);
                var currentEdges=FaceEdges(Faces(plan.Ids[0]));
                var liveEdges=plan.EdgeIdentities.Select(identity=>EdgeTopology.Resolve(identity,currentEdges)).ToArray();
                if(liveEdges.Length==0||liveEdges.Distinct().Count()!=liveEdges.Length)throw new InvalidOperationException("当前边集合不唯一");
                if(!SearchManager.CreateSolidChamfer(SolidChamferMethod.OneDistance,solid,liveEdges,null,null,r.ChamferDistance,r.ChamferDistance,false,false,"MastercamPluginAI.GeometryAdapter selected edges"))throw new InvalidOperationException("实体倒角失败");
                if(Get(solid.GetEntityID()) is not SolidGeometry||Faces(solid.GetEntityID()).Select(f=>f.Pid).SequenceEqual(plan.Original[0].Faces.Select(f=>f.Pid)))throw new InvalidOperationException("倒角后拓扑未发生可验证变化");
                break;
            case GeometryCommand.AssignLevel:
                foreach(int id in plan.Ids){var g=Get(id);g.Level=r.Level;if(!g.Commit()||Get(id).Level!=r.Level)throw new InvalidOperationException("图层属性回读失败");}
                break;
            default:throw new ArgumentException("未知命令");
            }
            RestoreFlags(plan.Original);
        },()=>{
            OutsideUnchanged(scene,plan.Ids,created);
            foreach(int id in created){var g=Get(id);if(!g.Validate()||g.Color!=r.Color||g.Level!=r.Level||g.Selected)throw new InvalidOperationException("新图素属性回读失败");}
            if(r.Command==GeometryCommand.DimensionBounds||r.Command==GeometryCommand.MergeCurves)SameStates(plan.Original);
            if(r.Command==GeometryCommand.DimensionBounds){var segments=DimensionWireframe.Create(plan.Before,r.TextHeight,r.DimensionOffset,r.Decimals);if(segments.Length!=created.Count)throw new InvalidOperationException("标注线段数不符");for(int i=0;i<segments.Length;i++){var line=Get(created[i]) as LineGeometry;if(line==null||!V(line.EndPoint1).Near(segments[i].A,1e-7)||!V(line.EndPoint2).Near(segments[i].B,1e-7))throw new InvalidOperationException("标注端点回读不符");}}
            if(r.Command==GeometryCommand.AssignLevel){foreach(var old in plan.Original){var a=State(Get(old.Id),true);if(!old.Equivalent(a,false,false)||a.Level!=r.Level||a.Color!=old.Color||a.Selected!=old.Selected||a.Blanked!=old.Blanked||!old.Faces.Zip(a.Faces).All(p=>p.First.Color==p.Second.Color&&p.First.ColorSource==p.Second.ColorSource))throw new InvalidOperationException("图层修改回读不符");}}
            if(r.Command is GeometryCommand.CenterXY or GeometryCommand.CenterXYZ or GeometryCommand.RotateX90 or GeometryCommand.RotateY90 or GeometryCommand.RotateZ90 or GeometryCommand.AlignCplane){
                if(!Measure(plan.Ids,world).Near(expected,1e-6))throw new InvalidOperationException("变换结果包围盒与预期不符");
                VerifyTransformedPoints(plan,world);
            }
            if(r.Command is GeometryCommand.PaintZPlanes or GeometryCommand.PaintVerticalPlanes){
                foreach(var old in plan.Original){var after=State(Get(old.Id),true);if(!old.Equivalent(after,false,false)||old.Color!=after.Color||old.Level!=after.Level||old.Selected!=after.Selected||old.Blanked!=after.Blanked)throw new InvalidOperationException("着色改变了几何或实体属性");
                    foreach(var f in after.Faces){bool target=plan.Faces.Any(p=>p.Body==f.Body&&p.Pid==f.Pid);var prior=old.Faces.Single(x=>x.Pid==f.Pid);if(target?f.Color!=r.Color||f.ColorSource!=Colors.FaceColorResult.ColorFromFace.ToString():f.Color!=prior.Color||f.ColorSource!=prior.ColorSource)throw new InvalidOperationException("面颜色回读不符");}}
            }
        },()=>{RestoreFlags(plan.Original);context.Restore();},()=>{
            OutsideUnchanged(scene,plan.Ids,Array.Empty<int>());SameStates(plan.Original);
            if(!Measure(plan.Ids,r.Command==GeometryCommand.AlignCplane?cp:world).Near(plan.Before,1e-6))throw new InvalidOperationException("回滚包围盒不一致");
        });
        return created.ToArray();
    }
    private static IEnumerable<V3> Corners(Bounds3 b){foreach(double x in new[]{b.Min.X,b.Max.X})foreach(double y in new[]{b.Min.Y,b.Max.Y})foreach(double z in new[]{b.Min.Z,b.Max.Z})yield return new(x,y,z);}
    private static void VerifyTransformedPoints(GeometryPlan p,MCView world)
    {
        var r=p.Request;V3 Convert(V3 v){
            if(r.Command==GeometryCommand.AlignCplane)return p.SourceFrame.ToLocal(v);
            if(r.Command is GeometryCommand.CenterXY or GeometryCommand.CenterXYZ)return v+GeometryMath.CenterDelta(p.Before,r.Destination,r.Command==GeometryCommand.CenterXYZ);
            var axis=r.Command==GeometryCommand.RotateX90?new V3(1,0,0):r.Command==GeometryCommand.RotateY90?new V3(0,1,0):new V3(0,0,1);return GeometryMath.Rotate(v,p.Before.Center,axis,r.QuarterTurns*90);
        }
        foreach(var old in p.Original){var actual=State(Get(old.Id),true);if(actual.Level!=old.Level||actual.Color!=old.Color||actual.Selected!=old.Selected||actual.Blanked!=old.Blanked||actual.Type!=old.Type||actual.Points.Length!=old.Points.Length)throw new InvalidOperationException("变换属性改变");
            for(int i=0;i<old.Points.Length;i++)if(!Convert(old.Points[i]).Near(actual.Points[i],1e-6))throw new InvalidOperationException("变换端点回读失败");
            foreach(var face in old.Faces){var f=actual.Faces.SingleOrDefault(a=>a.Pid==face.Pid)??throw new InvalidOperationException("刚体变换后面 PID 丢失");if(face.Color!=f.Color||face.ColorSource!=f.ColorSource)throw new InvalidOperationException("刚体变换后面颜色改变");
                var n=Convert(face.Normal)-Convert(new());if(face.Normal.Length>0.5&&!n.Near(f.Normal,1e-6))throw new InvalidOperationException("刚体变换后法向回读失败");}
        }
    }
}
