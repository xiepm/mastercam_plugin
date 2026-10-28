using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Windows.Forms;
using Mastercam.App.Types;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Math;
using Mastercam.Operations;
using Mastercam.Support;

namespace Workshop2027;

public sealed partial class Main
{
    public MCamReturn NearestView(int p) => Call(()=>Workflow.SnapView(Workflow.LoadViewOptions()));
    public MCamReturn ViewOptions(int p) => Call(WorkflowUi.ViewSettings);
    public MCamReturn StockSetup(int p) => Call(WorkflowUi.Stock);
    public MCamReturn InsertAfter(int p) => Call(()=>{ Work.SelectedIds(); if(!ExternalAppsManager.RunFTCommand("Mastercam","OMarrowRight"))throw new InvalidOperationException("插入箭头命令未执行。"); });
    public MCamReturn ImportOperations(int p) => Call(()=>Workflow.ExistingModule("LittleBee.Rebuilt.Exchange","ShowImport"));
    public MCamReturn PorscheBoundary(int p) => Forward("PorscheAdvanced2027","Boundary");
    public MCamReturn PorscheHealing(int p) => Forward("PorscheAdvanced2027","Healing");
    public MCamReturn PorscheHoles(int p) => Forward("PorscheAdvanced2027","Holes");
    public MCamReturn OperationTools(int p) => Forward("OperationTools2027","OpenHub");
    public MCamReturn GeometryTools(int p) => Forward("GeometryTools2027","Show");
    public MCamReturn NativeGeometry(int p) => Forward("GeometryTools2027.NativeCommands","Show");
    public MCamReturn LevelExport(int p) => Forward("LevelExport2027","Show");
    public MCamReturn ChainTools(int p) => Forward("ChainTools2027","Show");
    public MCamReturn SvgGeometry(int p) => Forward("SVGGeometry2027","Show");
    public MCamReturn HirthTools(int p) => Forward("HirthTools2027","Show");
    public MCamReturn SolidBoundary(int p) => Forward("SolidBoundary2027","Show");
    public MCamReturn AdvancedDrill(int p) => Forward("AdvancedDrill2027","Show");
    public MCamReturn TapDrill(int p) => Forward("AdvancedDrillTap2027","Show");
    public MCamReturn TpSketcher(int p) => Forward("TpSketcher2027","Show");
    public MCamReturn HolderTools(int p) => Forward("HolderTools2027","Show");
    public MCamReturn ScreenTools(int p) => Forward("ScreenTools2027","Show");
    public MCamReturn SurfaceNormals(int p) => Forward("MPDesignTools2027","ReverseSelectedNormals");
    public MCamReturn MPEdges3D(int p) => Forward("MPEdgeTools2027","ShowEdges3D");
    public MCamReturn MPEdges2D(int p) => Forward("MPEdgeTools2027","ShowEdges2D");
    public MCamReturn AnalyticRadius(int p) => Forward("MPDesignRadiusSelect2027","SelectByAnalyticRadius");
    public MCamReturn SurfaceTypes(int p) => Forward("MPDesignSurfaceSelect2027","SelectVisibleSurfaceTypes");
    public MCamReturn HsmPocket(int p) => Forward("HSMRebuild2027","CreatePocket");
    public MCamReturn HsmReadback(int p) => Forward("HSMRebuild2027","Readback");
    public MCamReturn HsmCalculate(int p) => Forward("HSMRebuild2027","Recalculate");
    public MCamReturn HsmRollback(int p) => Forward("HSMRebuild2027","Rollback");
    public MCamReturn MpSections(int p) => Forward("MPRebuild2027","Sections");
    public MCamReturn MpSliceStack(int p) => Forward("MPRebuild2027","SliceStack");
    public MCamReturn MpDraft(int p) => Forward("MPRebuild2027","DraftAnalysis");
    public MCamReturn MpParting(int p) => Forward("MPRebuild2027","PartingPreparation");
    public MCamReturn MpNormals(int p) => Forward("MPRebuild2027","FacetNormals");
    public MCamReturn ElectrodeReport(int p) => Forward("ElectrodeReport2027.UI","Show");
    public MCamReturn OriginalSwitchBG(int p) => Forward("SwitchBG","m_main");
    public MCamReturn OriginalChainIt(int p) => Forward("ChainIt","m_main");
    public MCamReturn OriginalHirth(int p) => Forward("Hirth","m_main");
    public MCamReturn OriginalSetupSheet(int p) => Forward("SetupSheet","m_main");
    public MCamReturn OriginalToolList(int p) => Forward("ToolList","m_main");
    public MCamReturn OriginalElectrodes(int p) => Forward("ElectrodesReport","m_main");
    public MCamReturn OriginalMergeFixture(int p) => Forward("MergeFixture","m_main");
    public MCamReturn OriginalFixtureSetup(int p) => Forward("FixtureSetup","m_main");
    public MCamReturn OriginalSketch(int p) => Forward("TpSketcher","m_main");
    public MCamReturn OriginalSnapshot(int p) => Forward("XSnapShot","m_main");
    public MCamReturn OriginalRenameNCI(int p) => Forward("RenameNCI","m_main");
    public MCamReturn OriginalHolder(int p) => Forward("Holder_CH","m_main");
    public MCamReturn OriginalSVG(int p) => Forward("SVGImage","m_main");
    public MCamReturn OriginalSTL(int p) => Forward("Level2STL","m_main");
    public MCamReturn OriginalOffset(int p) => Forward("SetWorkoffset","m_main");
    public MCamReturn Fixtures(int p) => Forward("FixtureTools2027","Show");
}

public sealed record ViewOptions(bool Construction=false,bool Tool=false,bool Wcs=false);

public static class Workflow
{
    static string ViewOptionsPath=>Path.Combine(Work.DataRoot,"view-options.json");
    public static ViewOptions LoadViewOptions()=>File.Exists(ViewOptionsPath)?JsonSerializer.Deserialize<ViewOptions>(File.ReadAllText(ViewOptionsPath))??new ViewOptions():new ViewOptions();
    public static void SaveViewOptions(ViewOptions value){var tmp=ViewOptionsPath+".tmp";File.WriteAllText(tmp,JsonSerializer.Serialize(value));File.Move(tmp,ViewOptionsPath,true);}
    public static void ExistingModule(string type,string method)
    {
        string file=Path.Combine(Path.GetDirectoryName(typeof(Main).Assembly.Location),"..","LittleBee2027","LittleBee2027.dll");
        var asm=Assembly.LoadFrom(Path.GetFullPath(file));
        var target=asm.GetType(type)?.GetMethod(method,BindingFlags.Public|BindingFlags.Static,null,Type.EmptyTypes,null)??throw new MissingMethodException("已安装模块缺少此入口，请查看安装说明。");
        try {target.Invoke(null,null);}catch(TargetInvocationException e){throw e.InnerException??e;}
    }
    public static double[][] OrthogonalCandidates()
    {
        var axes=new[]{new[]{1.0,0,0},new[]{0.0,1,0},new[]{0.0,0,1},new[]{-1.0,0,0},new[]{0.0,-1,0},new[]{0.0,0,-1}};
        var result=new List<double[]>();
        foreach(var normal in axes)foreach(var right in axes){
            if(System.Math.Abs(normal.Zip(right,(a,b)=>a*b).Sum())>0.1)continue;
            var up=new[]{normal[1]*right[2]-normal[2]*right[1],normal[2]*right[0]-normal[0]*right[2],normal[0]*right[1]-normal[1]*right[0]};
            result.Add(right.Concat(up).Concat(normal).ToArray());
        }
        // Stable identity-first tie handling; exactly 24 proper signed-axis rotations.
        return result.OrderByDescending(a=>a[0]+a[4]+a[8]).ThenBy(a=>string.Join(",",a)).ToArray();
    }
    public static double[] NearestMatrix(double[] matrix)
    {
        if(matrix==null||matrix.Length!=9||matrix.Any(x=>!double.IsFinite(x)))throw new ArgumentException("视图矩阵无效。");
        foreach(int r in new[]{0,1,2})if(System.Math.Abs(Enumerable.Range(0,3).Sum(c=>matrix[r*3+c]*matrix[r*3+c])-1)>1e-5)throw new ArgumentException("视图矩阵不是单位正交矩阵。");
        for(int i=0;i<3;i++)for(int j=i+1;j<3;j++)if(System.Math.Abs(Enumerable.Range(0,3).Sum(c=>matrix[i*3+c]*matrix[j*3+c]))>1e-5)throw new ArgumentException("视图矩阵轴不正交。");
        double determinant=matrix[0]*(matrix[4]*matrix[8]-matrix[5]*matrix[7])-matrix[1]*(matrix[3]*matrix[8]-matrix[5]*matrix[6])+matrix[2]*(matrix[3]*matrix[7]-matrix[4]*matrix[6]);
        if(System.Math.Abs(determinant-1)>1e-5)throw new ArgumentException("视图矩阵含镜像。");
        return OrthogonalCandidates().OrderBy(a=>new[]{0,1,2,6,7,8}.Sum(i=>System.Math.Abs(matrix[i]-a[i]))).First();
    }
    static double[] Flat(Matrix3D m)=>Enumerable.Range(0,9).Select(i=>m[i/3,i%3]).ToArray();
    static bool Same(Matrix3D a,Matrix3D b)=>Flat(a).Zip(Flat(b),(x,y)=>System.Math.Abs(x-y)).All(x=>x<1e-7);
    static bool Same(Point3D a,Point3D b)=>System.Math.Abs(a.x-b.x)<1e-7&&System.Math.Abs(a.y-b.y)<1e-7&&System.Math.Abs(a.z-b.z)<1e-7;
    public static short SnapView(ViewOptions options)
    {
        if(options==null)throw new ArgumentNullException(nameof(options));
        var oldG=ViewManager.GraphicsView;var oldC=ViewManager.CPlane;var oldT=ViewManager.TPlane;var oldW=ViewManager.WorkCoordinateSystem;
        var a=NearestMatrix(Flat(oldG.ViewMatrix));
        var matrix=new Matrix3D(new Point3D(a[0],a[1],a[2]),new Point3D(a[3],a[4],a[5]),new Point3D(a[6],a[7],a[8]));
        var zero=new Point3D(0,0,0);var existing=ViewManager.GetAllViews(false)??Array.Empty<MCView>();
        var plane=existing.FirstOrDefault(v=>Same(v.ViewMatrix,matrix)&&Same(v.ViewOrigin,zero));
        short ownedId=0;string ownedName=null,allocatedName=null;
        bool cg=ViewManager.CplaneFollowsGplane,gw=ViewManager.GplaneFollowsWcs,cw=ViewManager.CplaneFollowsWcs;
        try{
            ViewManager.CplaneFollowsGplane=false;ViewManager.GplaneFollowsWcs=false;ViewManager.CplaneFollowsWcs=false;
            if(plane==null){
                if(UndoManager.IsTransactionActive()||!UndoManager.StartTransaction())throw new InvalidOperationException("请先结束当前编辑。");
                try{
                    plane=new MCView();
                    if(!plane.Commit()||existing.Any(v=>v.ViewID==plane.ViewID))throw new InvalidOperationException("无法分配新正交视图。");
                    ownedId=plane.ViewID;allocatedName=plane.ViewName;ownedName="工艺助手-正交-"+ownedId;
                    plane.ViewName=ownedName;plane.ViewMatrix=matrix;plane.ViewOrigin=zero;
                    if(!plane.Commit()||!plane.Retrieve()||!Same(plane.ViewMatrix,matrix)||!Same(plane.ViewOrigin,zero))throw new InvalidOperationException("正交视图回读失败。");
                    UndoManager.CommitTransaction();
                }catch{if(UndoManager.IsTransactionActive())UndoManager.CancelTransaction();throw;}
            }
            if(options.Wcs)ViewManager.WorkCoordinateSystem=plane;
            if(options.Construction)ViewManager.CPlane=plane;
            if(options.Tool)ViewManager.TPlane=plane;
            ViewManager.GraphicsView=plane;
            if(!Same(ViewManager.GraphicsView.ViewMatrix,matrix)||(options.Construction&&!Same(ViewManager.CPlane.ViewMatrix,matrix))||(options.Tool&&!Same(ViewManager.TPlane.ViewMatrix,matrix))||(options.Wcs&&!Same(ViewManager.WorkCoordinateSystem.ViewMatrix,matrix)))throw new InvalidOperationException("视图切换回读失败。");
            return plane.ViewID;
        }catch{
            ViewManager.WorkCoordinateSystem=oldW;ViewManager.CPlane=oldC;ViewManager.TPlane=oldT;ViewManager.GraphicsView=oldG;
            if(ownedId>7){var v=(ViewManager.GetAllViews(false)??Array.Empty<MCView>()).FirstOrDefault(x=>x.ViewID==ownedId);if(v!=null&&(v.ViewName==ownedName||v.ViewName==allocatedName)&&!v.IsInUseView&&!v.IsLockedView)v.Delete();}
            throw;
        }finally{ViewManager.CplaneFollowsGplane=cg;ViewManager.GplaneFollowsWcs=gw;ViewManager.CplaneFollowsWcs=cw;GraphicsManager.Repaint();}
    }
    public static MillStockData CloneStock(MillStockData source)
    {
        var copy=new MillStockData();foreach(var p in typeof(MillStockData).GetProperties(BindingFlags.Public|BindingFlags.Instance).Where(p=>p.CanRead&&p.CanWrite&&p.GetIndexParameters().Length==0))p.SetValue(copy,p.GetValue(source));return copy;
    }
    public static void SetRectangularStock(int groupId,Point3D size,Point3D origin,StockOriginPosition anchor,short planeId)
    {
        if(!new[]{size.x,size.y,size.z}.All(x=>double.IsFinite(x)&&x>0)||!new[]{origin.x,origin.y,origin.z}.All(double.IsFinite)||!Enum.IsDefined(anchor))throw new ArgumentException("尺寸必须为有限正数，原点和定位方式必须有效。");
        var before=MillStock.GetStockData(groupId)??throw new InvalidOperationException("请选择铣削机床群组。");
        var plane=(ViewManager.GetAllViews(false)??Array.Empty<MCView>()).SingleOrDefault(v=>v.ViewID==planeId)??throw new ArgumentException("毛坯平面不存在。");
        var next=CloneStock(before);next.StockShape=StockShapes.Rectangle;next.StockSize=size;next.StockOrigin=origin;next.StockOriginLocation=anchor;next.StockPlaneID=plane.ViewID;next.StockPlaneName=plane.ViewName;next.DisplayStock=true;
        try{
            if(!MillStock.SetStockData(next,groupId))throw new InvalidOperationException("毛坯写入失败。");
            var read=MillStock.GetStockData(groupId);
            if(read==null||read.StockShape!=StockShapes.Rectangle||!Same(read.StockSize,size)||!Same(read.StockOrigin,origin)||read.StockOriginLocation!=anchor||read.StockPlaneID!=planeId)throw new InvalidOperationException("毛坯回读未通过。");
        }catch(Exception cause){
            if(!MillStock.SetStockData(before,groupId))throw new AggregateException("毛坯恢复失败，请检查机床群组。",cause);
            var restored=MillStock.GetStockData(groupId);if(restored==null||restored.StockShape!=before.StockShape||!Same(restored.StockSize,before.StockSize)||!Same(restored.StockOrigin,before.StockOrigin)||restored.StockPlaneID!=before.StockPlaneID)throw new AggregateException("原毛坯恢复回读失败。",cause);
            throw;
        }finally{OperationsManager.InitOperationsManagerTree();GraphicsManager.Repaint();}
    }
}

public static class WorkflowUi
{
    static IWin32Window Owner=>Mastercam.UI.MastercamWindow.GetHandle();
    static Form Form(string title,int w,int h)=>new Form{Text=title,ClientSize=new Size(w,h),Font=new Font("Microsoft YaHei UI",10),StartPosition=FormStartPosition.CenterParent,AutoScaleMode=AutoScaleMode.Dpi,MinimizeBox=false};
    public static void ViewSettings()
    {
        var value=Workflow.LoadViewOptions();using var f=Form("最近正交视图 · 跟随设置",530,255);
        f.Controls.Add(new Label{Text="按当前图形朝向选择最近的世界正交方向（含 90° 滚转）。",Left=20,Top=20,Width=490,Height=45});
        var c=new CheckBox{Text="同时设置构图平面",Checked=value.Construction,Left=25,Top=80,Width=250};var t=new CheckBox{Text="同时设置刀具平面",Checked=value.Tool,Left=25,Top=115,Width=250};var w=new CheckBox{Text="同时设置 WCS",Checked=value.Wcs,Left=25,Top=150,Width=250};f.Controls.AddRange(new Control[]{c,t,w});
        var ok=new Button{Text="保存",Left=390,Top=200,Width=110};ok.Click+=(s,e)=>{try{Workflow.SaveViewOptions(new ViewOptions(c.Checked,t.Checked,w.Checked));f.Close();}catch(Exception ex){Ui.Error(ex);}};f.Controls.Add(ok);f.ShowDialog(Owner);
    }
    public static void Stock()
    {
        var group=GroupManager.GetActiveMachineGroup()??throw new InvalidOperationException("请选择机床群组。");var data=MillStock.GetStockData(group.ID)??throw new InvalidOperationException("当前机床群组没有可读铣削毛坯。");
        using var f=Form("矩形毛坯 · "+group.Name,720,350);f.Controls.Add(new Label{Text="尺寸与原点使用当前文档单位；原点按下方定位方式解释。",Left=20,Top=16,Width=670});
        var nums=new NumericUpDown[6];double[] init={data.StockSize.x,data.StockSize.y,data.StockSize.z,data.StockOrigin.x,data.StockOrigin.y,data.StockOrigin.z};
        for(int i=0;i<6;i++){int row=i/3,col=i%3;f.Controls.Add(new Label{Text=(row==0?"尺寸 ":"原点 ")+"XYZ"[col],Left=20+col*230,Top=60+row*66,Width=200});nums[i]=new NumericUpDown{Left=20+col*230,Top=83+row*66,Width=205,DecimalPlaces=5,Minimum=row==0?0.00001m:-10000000m,Maximum=10000000m,Value=(decimal)System.Math.Clamp(double.IsFinite(init[i])?init[i]:0,row==0?0.00001:-10000000,10000000)};f.Controls.Add(nums[i]);}
        var views=ViewManager.GetAllViews(false);var plane=new ComboBox{Left=20,Top=232,Width=330,DropDownStyle=ComboBoxStyle.DropDownList};plane.Items.AddRange(views.Select(v=>(object)(v.ViewID+" · "+v.ViewName)).ToArray());plane.SelectedIndex=System.Math.Max(0,Array.FindIndex(views,v=>v.ViewID==data.StockPlaneID));
        var anchors=Enum.GetValues<StockOriginPosition>();string[] names={"顶面中心","顶面左上","顶面右上","顶面右下","顶面左下","底面左上","底面右上","底面右下","底面左下","体积中心","底面中心"};var anchor=new ComboBox{Left=375,Top=232,Width=315,DropDownStyle=ComboBoxStyle.DropDownList};anchor.Items.AddRange(names.Cast<object>().ToArray());anchor.SelectedIndex=Array.IndexOf(anchors,data.StockOriginLocation);
        f.Controls.AddRange(new Control[]{new Label{Text="毛坯平面",Left=20,Top=207},new Label{Text="原点定位",Left=375,Top=207},plane,anchor});
        var apply=new Button{Text="应用并回读",Left=535,Top=292,Width=155,Height=36};apply.Click+=(s,e)=>{try{if(plane.SelectedIndex<0||anchor.SelectedIndex<0)throw new InvalidOperationException("请选择毛坯平面与原点定位。");Workflow.SetRectangularStock(group.ID,new Point3D((double)nums[0].Value,(double)nums[1].Value,(double)nums[2].Value),new Point3D((double)nums[3].Value,(double)nums[4].Value,(double)nums[5].Value),anchors[anchor.SelectedIndex],views[plane.SelectedIndex].ViewID);f.Close();Ui.Info("矩形毛坯已设置，尺寸、原点与平面回读一致。");}catch(Exception ex){Ui.Error(ex);}};f.Controls.Add(apply);f.ShowDialog(Owner);
    }
}
