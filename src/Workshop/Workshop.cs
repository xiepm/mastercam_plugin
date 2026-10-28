using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;
using Mastercam.App;
using Mastercam.App.Types;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Operations;
using Mastercam.Support;

[assembly: System.Reflection.AssemblyVersion("2.7.1.0")]
[assembly: System.Runtime.Versioning.TargetFramework(".NETCoreApp,Version=v10.0")]
namespace Workshop2027;

public sealed partial class Main : NetHook3App
{
    public override int Version(int p) => (int)MCamDefines.NetHookLibraryVersion;
    public override MCamReturn Init(int p) => MCamReturn.NoErrors;
    public override MCamReturn Run(int p) => OpenHub(p);
    public MCamReturn OpenHub(int p) => Call(Ui.Hub);
    public MCamReturn InstallRibbon(int p) => Call(() => { if(!Ribbon.Install()) throw new InvalidOperationException("无法添加工艺助手功能区。"); });
    public MCamReturn BatchGroups(int p) => Call(Ui.Groups);
    public MCamReturn BatchParameters(int p) => Call(Ui.Parameters);
    public MCamReturn CheckPlanes(int p) => Call(Ui.Planes);
    public MCamReturn MatchPlanes(int p) => Call(Ui.MatchPlanes);
    public MCamReturn AlignView(int p) => Call(() => { ViewManager.GraphicsView=ViewManager.CPlane; GraphicsManager.FitScreen(); GraphicsManager.Repaint(); });
    public MCamReturn EditOperation(int p) => Forward("LittleBee2027","EditOperation");
    public MCamReturn EditTool(int p) => Forward("LittleBee2027","EditTool");
    public MCamReturn EditGeometry(int p) => Forward("LittleBee2027","EditOperationGeometry");
    public MCamReturn CommonParameters(int p) => Forward("LittleBee2027","EditCommonParameters");
    public MCamReturn FollowPlanes(int p) => Forward("LittleBee2027","ChangeView");
    public MCamReturn RenameNci(int p) => Forward("LittleBee2027","ChangeNci");
    public MCamReturn CopyOperations(int p) => Forward("LittleBee2027","CopyOperation");
    public MCamReturn PasteOperations(int p) => Forward("LittleBee2027","PasteOperation");
    public MCamReturn Templates(int p) => Call(() => Workflow.ExistingModule("LittleBee.Rebuilt.Exchange","ShowImport"));
    public MCamReturn SetupSheet(int p) => Forward("SetupSheets2027","Show");
    public MCamReturn MiddleConfirm(int p) => Forward("MiddleConfirm2027","Configure");
    public MCamReturn Usage(int p) => Call(() => Ui.OpenFolder(Path.GetDirectoryName(typeof(Main).Assembly.Location)));
    static MCamReturn Forward(string app,string command) => Call(() => { if(!ExternalAppsManager.RunFTCommand(app,command)) throw new InvalidOperationException(app+"."+command+" 未成功执行，请查看安装记录。"); });
    static MCamReturn Call(Action action) { try { action(); return MCamReturn.NoErrors; } catch(Exception e) { Ui.Error(e); return MCamReturn.ErrorOccurred; } }
}

public record PlaneRow(int Id,string Name,int Wcs,int Construction,int Tool,string WcsName,string ConstructionName,string ToolName,bool Equal);
public record ParameterRow(int Id,string Name,double Feed,double Spindle,bool Css,bool Locked,bool Dirty,string Kind,double? Wall,double? Floor);
public static class Work
{
    public static string DataRoot { get {var p=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MC2027Workshop");Directory.CreateDirectory(p);return p;} }
    public static int[] SelectedIds() {var a=SearchManager.GetOperationIDs(false)??Array.Empty<int>();if(a.Length==0)throw new InvalidOperationException("请先在刀路管理器中选择工序。");return a;}
    public static PlaneRow[] ReadPlanes(int[] ids) => ids.Select(id=> {var d=SearchManager.GetOperationData(id); if(d==null||!d.IsValid)throw new InvalidOperationException("无法读取工序 "+id);return new PlaneRow(id,d.Comment,d.WCSPlaneID,d.ConstructionPlaneID,d.ToolPlaneID,d.WCSPlaneName,d.ConstructionPlaneName,d.ToolPlaneName,d.WCSPlaneID==d.ConstructionPlaneID&&d.WCSPlaneID==d.ToolPlaneID);}).ToArray();
    public static ParameterRow[] ReadParameters(int[] ids) => ids.Select(id=> {var d=SearchManager.GetOperationData(id);if(d==null||!d.IsValid)throw new InvalidOperationException("无法读取工序 "+id);Operation op=null;try{op=SearchManager.GetOperation(id);}catch{} var stock=Stock(op);return new ParameterRow(id,d.Comment,d.FeedRate,d.SpindleSpeed,d.IsSpindleCSS,d.Locked,d.Dirty,op?.GetType().Name??"SDK 不支持编辑",stock.wall,stock.floor);}).ToArray();
    static (double? wall,double? floor) Stock(Operation op) => op switch {ContourOperation c=>(c.CutParams.LeaveStock.OnWalls,c.CutParams.LeaveStock.OnFloors),PocketOperation c=>(c.CutParams.LeaveStock.OnWalls,c.CutParams.LeaveStock.OnFloors),FacingOperation c=>(c.CutParams.LeaveStock.OnWalls,c.CutParams.LeaveStock.OnFloors),_=>(null,null)};
    static void SetStock(Operation op,double? wall,double? floor)
    {
        switch(op) {
            case ContourOperation c: if(wall.HasValue)c.CutParams.LeaveStock.OnWalls=wall.Value;if(floor.HasValue)c.CutParams.LeaveStock.OnFloors=floor.Value;break;
            case PocketOperation c: if(wall.HasValue)c.CutParams.LeaveStock.OnWalls=wall.Value;if(floor.HasValue)c.CutParams.LeaveStock.OnFloors=floor.Value;break;
            case FacingOperation c: if(wall.HasValue)c.CutParams.LeaveStock.OnWalls=wall.Value;if(floor.HasValue)c.CutParams.LeaveStock.OnFloors=floor.Value;break;
            default: throw new InvalidOperationException("余量编辑仅支持原生二维外形、挖槽和平面铣工序。");
        }
    }
    static Operation[] Validate(int[] ids)
    {
        if(ids==null||ids.Length==0||ids.Distinct().Count()!=ids.Length)throw new ArgumentException("工序列表无效。");
        return ids.Select(id=> {var d=SearchManager.GetOperationData(id);if(d==null||!d.IsValid||d.Locked)throw new InvalidOperationException("工序无效或已锁定："+id); return SearchManager.GetOperation(id)??throw new InvalidOperationException("SDK 不支持编辑此工序："+id);}).ToArray();
    }
    static void Transaction(Action action,Action restore)
    {
        if(UndoManager.IsTransactionActive()||!UndoManager.StartTransaction())throw new InvalidOperationException("当前有未结束的编辑，请结束后重试。");
        try {action();UndoManager.CommitTransaction();}
        catch(Exception cause) {
            Exception cancelError=null;try{UndoManager.CancelTransaction();}catch(Exception e){cancelError=e;}
            // API29 undo cancellation does not restore committed operation parameters. Restore explicitly.
            try{restore();}catch(Exception restoreError){throw new AggregateException("写入失败且恢复未完成，请检查所选工序。",cause,restoreError);}
            if(cancelError!=null)throw new AggregateException("参数已恢复，撤消事务结束失败。",cause,cancelError);
            throw new InvalidOperationException("写入未通过，已恢复原值；工序可能仍标记为需要重算。",cause);
        }
        finally {OperationsManager.InitOperationsManagerTree();}
    }
    public static void SetParameters(int[] ids,double? feed,double? spindle,double? wall,double? floor)
    {
        if(feed==null&&spindle==null&&wall==null&&floor==null)throw new ArgumentException("至少勾选一个修改项。");
        foreach(var x in new[]{feed,spindle})if(x.HasValue&&(!double.IsFinite(x.Value)||x.Value<=0))throw new ArgumentException("进给与转速必须是有限正数。");
        if(spindle.HasValue&&(spindle.Value>int.MaxValue||spindle.Value!=Math.Truncate(spindle.Value)))throw new ArgumentException("主轴转速必须是有效整数 rpm。");
        foreach(var x in new[]{wall,floor})if(x.HasValue&&(!double.IsFinite(x.Value)||x.Value<0))throw new ArgumentException("预留量必须是有限非负数。");
        var ops=Validate(ids);var before=ReadParameters(ids);
        if(before.Any(r=>r.Css)&&spindle.HasValue)throw new InvalidOperationException("所选工序含恒线速度，不能按 rpm 批量设置。");
        // Only the types covered by the official 2D parameter wrappers are editable here.
        if(ops.Any(o=>o is not ContourOperation&&o is not PocketOperation&&o is not FacingOperation))throw new InvalidOperationException("批量数值编辑仅支持原生二维外形、挖槽和平面铣；其他工序请使用共同参数。");
        string audit=Path.Combine(DataRoot,"parameters-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+Guid.NewGuid().ToString("N").Substring(0,6)+".json");
        File.WriteAllText(audit,JsonSerializer.Serialize(new{State="Before",Document=FileManager.CurrentFileName,Before=before,feed,spindle,wall,floor},new JsonSerializerOptions{WriteIndented=true}));
        Transaction(()=> {
            foreach(var op in ops){if(feed.HasValue)op.FeedRate=feed.Value;if(spindle.HasValue)op.SpindleSpeed=checked((int)spindle.Value);if(wall.HasValue||floor.HasValue)SetStock(op,wall,floor);op.MarkDirty();if(!op.Commit(false))throw new InvalidOperationException("工序写入失败："+op.Name);}
            var after=ReadParameters(ids);for(int i=0;i<after.Length;i++){var a=after[i];bool Eq(double? wanted,double? actual)=>!wanted.HasValue||(actual.HasValue&&Math.Abs(wanted.Value-actual.Value)<1e-7);if(!Eq(feed,a.Feed)||!Eq(spindle,a.Spindle)||!Eq(wall,a.Wall)||!Eq(floor,a.Floor)||!a.Dirty)throw new InvalidOperationException("工序回读未通过："+a.Id);}
        },()=>{
            foreach(var saved in before){var op=SearchManager.GetOperation(saved.Id)??throw new InvalidOperationException("无法恢复工序 "+saved.Id);op.FeedRate=saved.Feed;op.SpindleSpeed=checked((int)saved.Spindle);SetStock(op,saved.Wall,saved.Floor);op.MarkDirty();if(!op.Commit(false))throw new InvalidOperationException("恢复写入失败："+saved.Id);}
            var read=ReadParameters(ids);for(int i=0;i<read.Length;i++){var a=read[i];var b=before[i];if(a.Feed!=b.Feed||a.Spindle!=b.Spindle||a.Wall!=b.Wall||a.Floor!=b.Floor)throw new InvalidOperationException("恢复回读失败："+a.Id);}
        });
        try {File.WriteAllText(audit,JsonSerializer.Serialize(new{State="Applied",Document=FileManager.CurrentFileName,Before=before,After=ReadParameters(ids)},new JsonSerializerOptions{WriteIndented=true}));}catch(Exception e){Ui.Info("参数已应用，但记录写入失败："+e.Message);}
    }
    public static void SetPlanes(int[] ids,MCView plane)
    {
        if(plane==null||plane.ViewID<1)throw new ArgumentException("坐标平面无效。");var ops=Validate(ids);
        if(ops.Any(o=>o is not ContourOperation&&o is not PocketOperation&&o is not FacingOperation))throw new InvalidOperationException("一键三面目前支持原生二维外形、挖槽和平面铣。");
        var prior=ops.Select(o=>new{Id=o.GetOperationID(),o.WCS,o.ConstructionPlane,o.ToolPlane,o.UseWCS,o.UseConstructionPlane,o.UseToolPlane}).ToArray();
        Transaction(()=> {foreach(var o in ops){o.WCS=plane;o.ConstructionPlane=plane;o.ToolPlane=plane;o.UseWCS=true;o.UseConstructionPlane=true;o.UseToolPlane=true;o.MarkDirty();if(!o.Commit(false))throw new InvalidOperationException("工序写入失败："+o.Name);}if(ReadPlanes(ids).Any(r=>!r.Equal||r.Wcs!=plane.ViewID))throw new InvalidOperationException("坐标平面回读未通过。");},()=>{
            foreach(var s in prior){var o=SearchManager.GetOperation(s.Id)??throw new InvalidOperationException("无法恢复工序 "+s.Id);o.WCS=s.WCS;o.ConstructionPlane=s.ConstructionPlane;o.ToolPlane=s.ToolPlane;o.UseWCS=s.UseWCS;o.UseConstructionPlane=s.UseConstructionPlane;o.UseToolPlane=s.UseToolPlane;o.MarkDirty();if(!o.Commit(false))throw new InvalidOperationException("恢复坐标失败："+s.Id);var r=ReadPlanes(new[]{s.Id})[0];if(r.Wcs!=s.WCS.ViewID||r.Construction!=s.ConstructionPlane.ViewID||r.Tool!=s.ToolPlane.ViewID)throw new InvalidOperationException("恢复坐标回读失败："+s.Id);}
        });
    }
    public static int[] CreateGroups(int parentId,string prefix,int start,int count)
    {
        if(count<1||count>200||start<0||start>999999-count)throw new ArgumentException("群组数量需为 1–200，序号需为 0–999799。");
        prefix=(prefix??"").Trim();if(prefix.Length==0||prefix.Length>40||prefix.Any(char.IsControl))throw new ArgumentException("群组前缀需为 1–40 个可见字符。");
        var parent=GroupManager.FindGroupByID(parentId)??throw new ArgumentException("父群组不存在。");
        var names=Enumerable.Range(start,count).Select(i=>prefix+i.ToString("D2")).ToArray();
        foreach(var n in names)if(GroupManager.FindGroupByName(n)!=null)throw new ArgumentException("群组已存在："+n);
        var created=new List<int>();
        try {foreach(var n in names){var g=GroupManager.NewGroup(parent,n)??throw new InvalidOperationException("新建群组失败："+n);created.Add(g.ID);if(GroupManager.FindGroupByID(g.ID)?.Name!=n)throw new InvalidOperationException("群组回读失败："+n);}}
        catch {foreach(var id in created.AsEnumerable().Reverse()){var failed=GroupManager.FindGroupByID(id);if(failed!=null)GroupManager.DeleteGroup(ref failed);}throw;}
        finally {OperationsManager.InitOperationsManagerTree();}
        return created.ToArray();
    }
}

public static class Ui
{
    static IWin32Window Owner=>Mastercam.UI.MastercamWindow.GetHandle();
    public static void Info(string text)=>MessageBox.Show(Owner,text,"工艺助手 2027",MessageBoxButtons.OK,MessageBoxIcon.Information);
    public static void Error(Exception e){try{File.AppendAllText(Path.Combine(Work.DataRoot,"errors.log"),DateTime.Now.ToString("s")+" "+e+Environment.NewLine);}catch{}MessageBox.Show(Owner,e.Message,"工艺助手 2027",MessageBoxButtons.OK,MessageBoxIcon.Error);}
    public static void OpenFolder(string path){if(!Directory.Exists(path))throw new DirectoryNotFoundException(path);System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path){UseShellExecute=true});}
    static Form Form(string title,int w=960,int h=540)=>new Form{Text=title,ClientSize=new Size(w,h),Font=new Font("Microsoft YaHei UI",10),StartPosition=FormStartPosition.CenterParent,AutoScaleMode=AutoScaleMode.Dpi,MinimizeBox=false};
    static DataGridView Grid(object rows)=>new DataGridView{DataSource=rows,Dock=DockStyle.Fill,ReadOnly=true,AllowUserToAddRows=false,AllowUserToDeleteRows=false,AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.DisplayedCells,SelectionMode=DataGridViewSelectionMode.FullRowSelect};
    public static void Hub()
    {
        using var f=Form("工艺助手 2027",820,480);var panel=new FlowLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(16),AutoScroll=true};f.Controls.Add(panel);
        foreach(var c in Ribbon.Commands.Where(c=>c.method!="OpenHub")){var cmd=c;var b=new Button{Text=c.label,Width=245,Height=66,Margin=new Padding(7)};b.Click+=(s,e)=>{f.Close();ExternalAppsManager.PostFTCommand("Workshop2027",cmd.method);};panel.Controls.Add(b);}f.ShowDialog(Owner);
    }
    public static void Groups()
    {
        var parent=GroupManager.GetActiveGroup();if(parent==null)throw new InvalidOperationException("请先选择机床群组或刀路群组。");
        using var f=Form("批量创建刀路群组",520,250);var label=new Label{Text="父群组："+parent.Name,Left=20,Top=15,Width=470};f.Controls.Add(label);
        var prefix=new TextBox{Text="工序组",Left=140,Top=57,Width=330};var start=new NumericUpDown{Minimum=0,Maximum=999000,Value=1,Left=140,Top=103};var count=new NumericUpDown{Minimum=1,Maximum=200,Value=5,Left=350,Top=103};f.Controls.AddRange(new Control[]{prefix,start,count,new Label{Text="名称前缀",Left=20,Top=60},new Label{Text="起始序号",Left=20,Top=106},new Label{Text="数量",Left=290,Top=106}});
        var ok=new Button{Text="创建",Left=360,Top=180,Width=110};ok.Click+=(s,e)=>{try{int[] ids=Work.CreateGroups(parent.ID,prefix.Text,(int)start.Value,(int)count.Value);f.Close();Info("已创建 "+ids.Length+" 个群组。");}catch(Exception ex){Error(ex);}};f.Controls.Add(ok);f.ShowDialog(Owner);
    }
    public static void Planes()
    {
        int[] ids=Work.SelectedIds();using var f=Form("所选工序 · 三面检查");f.Controls.Add(Grid(Work.ReadPlanes(ids)));f.ShowDialog(Owner);
    }
    public static void MatchPlanes()
    {
        int[] ids=Work.SelectedIds();var plane=ViewManager.WorkCoordinateSystem;
        if(MessageBox.Show(Owner,"将 "+ids.Length+" 个已选工序的 WCS、构图平面和刀具平面设为当前 WCS："+plane?.ViewName+"。\n修改后需要重新计算刀路。","统一三面",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK)return;
        Work.SetPlanes(ids,plane);Info("已更新，坐标平面回读一致。请重新计算并检查刀路。");
    }
    public static void Parameters()
    {
        int[] ids=Work.SelectedIds();var before=Work.ReadParameters(ids);using var f=Form("批量编辑 · 原生二维外形 / 挖槽 / 平面铣",1120,620);
        var p=new Panel{Dock=DockStyle.Bottom,Height=160};f.Controls.Add(Grid(before));f.Controls.Add(p);p.BringToFront();
        string[] labels={"进给（原工序模式）","主轴转速 rpm","壁面余量（文档单位）","底面余量（文档单位）"};var checks=new CheckBox[4];var values=new NumericUpDown[4];
        for(int i=0;i<4;i++){checks[i]=new CheckBox{Text=labels[i],Left=18+i*274,Top=15,Width=265};values[i]=new NumericUpDown{Left=18+i*274,Top=47,Width=245,DecimalPlaces=i==1?0:4,Minimum=0,Maximum=1000000,Value=(decimal)(i==0?Math.Clamp(before[0].Feed,0,1000000):i==1?Math.Clamp(before[0].Spindle,0,1000000):0)};p.Controls.Add(checks[i]);p.Controls.Add(values[i]);}
        p.Controls.Add(new Label{Text="只修改勾选项；保留各工序原有进给模式。应用后标记为需要重算。",Left=20,Top=92,Width=820});var apply=new Button{Text="应用到 "+ids.Length+" 个工序",Left=900,Top=101,Width=190,Height=38};
        apply.Click+=(s,e)=>{try{double? Val(int i)=>checks[i].Checked?(double)values[i].Value:null;Work.SetParameters(ids,Val(0),Val(1),Val(2),Val(3));f.Close();Info("已应用并通过回读检查。请重新计算并检查刀路。");}catch(Exception ex){Error(ex);}};p.Controls.Add(apply);f.ShowDialog(Owner);
    }
}

public static class Ribbon
{
    public static readonly (string method,string label)[] Commands={
        ("PorscheBoundary","实体自动轮廓"),("PorscheHealing","自动删孔补面"),("PorscheHoles","复杂孔自动工序"),("OpenHub","工艺助手"),("BatchGroups","批量群组"),("BatchParameters","批量参数"),("CheckPlanes","检查三面"),("MatchPlanes","统一三面"),("AlignView","视图摆正"),
        ("EditOperation","刀路参数"),("EditTool","编辑刀具"),("EditGeometry","图形管理"),("CommonParameters","共同参数"),("FollowPlanes","平面跟随"),("RenameNci","NC 名称"),("CopyOperations","复制刀路"),("PasteOperations","粘贴刀路"),("Templates","刀路模板"),("SetupSheet","程序单"),("MiddleConfirm","中键确认"),("Usage","说明与记录"),
        ("NearestView","最近正交视图"),("ViewOptions","正交跟随设置"),("StockSetup","矩形毛坯"),("InsertAfter","插入箭头后移"),("ImportOperations","导入刀路"),("OperationTools","加工操作"),("GeometryTools","几何工具"),("Fixtures","夹具库"),("NativeGeometry","原生几何工具"),("LevelExport","按图层导出 STL"),
        ("ChainTools","串连选择"),("SvgGeometry","SVG 轮廓导入"),("HirthTools","分度平面"),("SolidBoundary","实体平面边界"),("AdvancedDrill","分阶段钻孔"),
        ("TpSketcher","草绘刀具路径"),("HolderTools","刀柄截面"),("ScreenTools","白底截图"),("SurfaceNormals","反转曲面法向"),("SurfaceTypes","按曲面类型选择"),("ElectrodeReport","电极几何报表"),("TapDrill","分阶段钻孔与攻牙"),("MPEdges3D","提取三维直边"),("MPEdges2D","直边投影到XY"),("OriginalSwitchBG","背景切换"),("OriginalChainIt","串连选择"),("OriginalHirth","分度拟合平面"),("OriginalSetupSheet","加工报表"),("OriginalToolList","刀具清单"),("OriginalElectrodes","电极报告"),("OriginalMergeFixture","添加夹具"),("OriginalFixtureSetup","夹具设置"),("OriginalSketch","草绘刀路"),("OriginalSnapshot","白底框选截图"),("OriginalRenameNCI","重命名NCI"),("OriginalHolder","几何创建刀柄"),("OriginalSVG","SVG导入"),("OriginalSTL","图层导出STL"),("OriginalOffset","操作坐标系编号"),("AnalyticRadius","按解析面半径选实体")};
    static bool installed;
    public static bool Install()
    {
        if(installed)return true;var b=new StringBuilder("<Ribbon><Tab Label=\"工艺助手\" KeyTip=\"WS\"><Groups>");
        var groups=new[]{("保时捷 / V++",new[]{"PorscheBoundary","PorscheHealing","PorscheHoles"}),("工序",new[]{"OpenHub","OperationTools","AdvancedDrill","TpSketcher","BatchGroups","BatchParameters","InsertAfter"}),("几何与装夹",new[]{"GeometryTools","NativeGeometry","ChainTools","SolidBoundary","StockSetup","Fixtures"}),("坐标与视图",new[]{"CheckPlanes","MatchPlanes","NearestView","ViewOptions","HirthTools"}),("编辑",new[]{"EditOperation","EditTool","HolderTools","EditGeometry","CommonParameters"}),("文件与辅助",new[]{"ImportOperations","Templates","SetupSheet","LevelExport","SvgGeometry","ScreenTools","MiddleConfirm"})};
        for(int g=0;g<groups.Length;g++){b.Append("<Group Label=\"").Append(groups[g].Item1).Append("\" FTCommand=\"Workshop2027.OpenHub\" KeyTip=\"G").Append(g+1).Append("\"><Elements>");foreach(var command in groups[g].Item2)b.Append("<Button FTCommand=\"Workshop2027.").Append(command).Append("\" LargeMode=\"Always\"/>");b.Append("</Elements></Group>");}b.Append("</Groups></Tab>");
        void Tab(string label,string key,(string name,string[] commands)[] sections)
        {
            b.Append("<Tab Label=\"").Append(label).Append("\" KeyTip=\"").Append(key).Append("\"><Groups>");
            for(int i=0;i<sections.Length;i++)
            {
                var section=sections[i];b.Append("<Group Label=\"").Append(section.name).Append("\" FTCommand=\"Workshop2027.").Append(section.commands[0]).Append("\" KeyTip=\"G").Append(i+1).Append("\"><Elements>");
                foreach(var command in section.commands)b.Append("<Button FTCommand=\"Workshop2027.").Append(command).Append("\" LargeMode=\"Always\"/>");
                b.Append("</Elements></Group>");
            }
            b.Append("</Groups></Tab>");
        }
        Tab("X+ 工具","XP",new[]{("几何与坐标",new[]{"ChainTools","HirthTools","SvgGeometry","SolidBoundary"}),("刀路与刀具",new[]{"AdvancedDrill","TapDrill","TpSketcher","HolderTools"}),("报表与截图",new[]{"ElectrodeReport","SetupSheet","ScreenTools","LevelExport"})});
        if (new[]{"ChainIt","Hirth","SVGImage","SetWorkoffset","TpSketcher","Holder_CH","MergeFixture","FixtureSetup","SetupSheet","ToolList","ElectrodesReport","Level2STL","RenameNCI","SwitchBG","XSnapShot"}.All(n => File.Exists(Path.GetFullPath(Path.Combine(Path.GetDirectoryName(typeof(Main).Assembly.Location), "..", n + ".ft")))))
        Tab("X+ 原版","XO",new[]{("几何与坐标",new[]{"OriginalChainIt","OriginalHirth","OriginalSVG","OriginalOffset"}),("刀路与夹具",new[]{"OriginalSketch","OriginalHolder","OriginalMergeFixture","OriginalFixtureSetup"}),("报告与输出",new[]{"OriginalSetupSheet","OriginalToolList","OriginalElectrodes","OriginalSTL","OriginalRenameNCI"}),("显示",new[]{"OriginalSwitchBG","OriginalSnapshot"})});
        Tab("MP 设计工具","MP",new[]{("曲面",new[]{"SurfaceNormals","SurfaceTypes","AnalyticRadius"}),("实体边线",new[]{"MPEdges3D","MPEdges2D"})});
        b.Append("</Ribbon>");installed=Mastercam.UI.Ribbon.InsertThirdPartyRibbonTabs(b.ToString());File.WriteAllText(Path.Combine(Work.DataRoot,"ribbon.log"),DateTime.Now.ToString("s")+" result="+installed);return installed;
    }
}
