using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace MastercamPluginAI.GeometryAdapter;

public readonly record struct V3(double X, double Y, double Z)
{
    public static V3 operator +(V3 a,V3 b)=>new(a.X+b.X,a.Y+b.Y,a.Z+b.Z);
    public static V3 operator -(V3 a,V3 b)=>new(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
    public static V3 operator *(V3 a,double b)=>new(a.X*b,a.Y*b,a.Z*b);
    public double Dot(V3 b)=>X*b.X+Y*b.Y+Z*b.Z;
    public V3 Cross(V3 b)=>new(Y*b.Z-Z*b.Y,Z*b.X-X*b.Z,X*b.Y-Y*b.X);
    public double Length=>Math.Sqrt(Dot(this));
    public bool Finite=>double.IsFinite(X)&&double.IsFinite(Y)&&double.IsFinite(Z)&&Math.Max(Math.Abs(X),Math.Max(Math.Abs(Y),Math.Abs(Z)))<=1e12;
    public V3 Unit(){if(!Finite||Length<1e-12)throw new ArgumentException("无效方向向量");return this*(1/Length);}
    public bool Near(V3 b,double tolerance)=> (this-b).Length<=tolerance;
}
public sealed record Bounds3(V3 Min,V3 Max)
{
    public V3 Center=>(Min+Max)*0.5;
    public V3 Size=>Max-Min;
    public void Validate(){if(!Min.Finite||!Max.Finite||Min.X>Max.X||Min.Y>Max.Y||Min.Z>Max.Z)throw new ArgumentException("无效包围盒");}
    public static Bounds3 Of(IEnumerable<V3> points){var a=points.ToArray();if(a.Length==0||a.Any(p=>!p.Finite))throw new ArgumentException("空或无效坐标");return new(new(a.Min(p=>p.X),a.Min(p=>p.Y),a.Min(p=>p.Z)),new(a.Max(p=>p.X),a.Max(p=>p.Y),a.Max(p=>p.Z)));}
    public bool Near(Bounds3 b,double tolerance)=>Min.Near(b.Min,tolerance)&&Max.Near(b.Max,tolerance);
}
public readonly record struct Frame3(V3 Origin,V3 X,V3 Y,V3 Z)
{
    public static Frame3 World=>new(new(),new(1,0,0),new(0,1,0),new(0,0,1));
    public void Validate(){if(!Origin.Finite||!X.Finite||!Y.Finite||!Z.Finite||Math.Abs(X.Length-1)>1e-8||Math.Abs(Y.Length-1)>1e-8||Math.Abs(Z.Length-1)>1e-8||Math.Abs(X.Dot(Y))>1e-8||Math.Abs(X.Dot(Z))>1e-8||Math.Abs(Y.Dot(Z))>1e-8||X.Cross(Y).Dot(Z)<1-1e-8)throw new ArgumentException("坐标系必须为右手正交单位轴");}
    public V3 ToLocal(V3 p){var d=p-Origin;return new(d.Dot(X),d.Dot(Y),d.Dot(Z));}
    public V3 ToWorld(V3 p)=>Origin+X*p.X+Y*p.Y+Z*p.Z;
}
public static class GeometryMath
{
    public static bool IsPlanarDirection(bool planar,V3 normal,bool horizontal,double angleDegrees)
    {
        if(!double.IsFinite(angleDegrees)||angleDegrees<0||angleDegrees>5)throw new ArgumentException("角容差应为 0–5 度");
        if(!planar)return false;
        var nz=Math.Abs(normal.Unit().Z);var a=angleDegrees*Math.PI/180;
        return horizontal ? nz>=Math.Cos(a)-1e-14 : nz<=Math.Sin(a)+1e-14;
    }
    public static V3 Rotate(V3 p,V3 pivot,V3 axis,double degrees)
    {
        if(!p.Finite||!pivot.Finite||!double.IsFinite(degrees)||Math.Abs(degrees)>36000)throw new ArgumentException("旋转参数无效");
        var n=axis.Unit();var q=p-pivot;var r=degrees*Math.PI/180;
        return pivot+q*Math.Cos(r)+n.Cross(q)*Math.Sin(r)+n*(n.Dot(q)*(1-Math.Cos(r)));
    }
    public static V3 CenterDelta(Bounds3 b,V3 destination,bool moveZ){b.Validate();if(!destination.Finite)throw new ArgumentException("目标无效");return new(destination.X-b.Center.X,destination.Y-b.Center.Y,moveZ?destination.Z-b.Center.Z:0);}
    // Reject ambiguous joins, branches, disconnected components and tolerance-chain bridging.
    public static int[] OrderSimpleChain(IReadOnlyList<(V3 A,V3 B)> edges,double tolerance)
    {
        if(edges.Count<2||edges.Count>10000||!double.IsFinite(tolerance)||tolerance<=0)throw new ArgumentException("串连至少两段，容差必须为正");
        var nodes=new List<List<V3>>();var links=new List<(int A,int B)>();
        int Node(V3 p){
            if(!p.Finite)throw new ArgumentException("端点无效");
            var candidates=Enumerable.Range(0,nodes.Count).Where(i=>nodes[i].Any(q=>q.Near(p,tolerance))).ToArray();
            if(candidates.Length>1)throw new ArgumentException("端点匹配含糊");
            if(candidates.Length==0){nodes.Add(new(){p});return nodes.Count-1;}
            int j=candidates[0];if(nodes[j].Any(q=>!q.Near(p,tolerance)))throw new ArgumentException("容差链桥接含糊");nodes[j].Add(p);return j;
        }
        foreach(var e in edges){int a=Node(e.A),b=Node(e.B);if(a==b)throw new ArgumentException("不接受退化段或单段闭合曲线");links.Add((a,b));}
        var adjacent=Enumerable.Range(0,nodes.Count).Select(_=>new List<int>()).ToArray();
        for(int i=0;i<links.Count;i++){adjacent[links[i].A].Add(i);adjacent[links[i].B].Add(i);}
        if(adjacent.Any(a=>a.Count>2))throw new ArgumentException("串连存在分支");
        int start=Array.FindIndex(adjacent,a=>a.Count==1);if(start<0)start=0;
        var used=new HashSet<int>();var order=new List<int>();int current=start;
        while(true){int next=adjacent[current].FirstOrDefault(i=>!used.Contains(i),-1);if(next<0)break;used.Add(next);var l=links[next];bool forward=l.A==current;order.Add(forward?next+1:-(next+1));current=forward?l.B:l.A;}
        if(used.Count!=edges.Count)throw new ArgumentException("串连不连通");
        return order.ToArray();
    }
}
public readonly record struct Segment3(V3 A,V3 B);
public static class DimensionWireframe
{
    // Original stroke geometry; no fonts, resources or code from the legacy binary.
    private static readonly int[][] DigitSegments={new[]{0,1,2,3,4,5},new[]{1,2},new[]{0,1,6,4,3},new[]{0,1,6,2,3},new[]{5,6,1,2},new[]{0,5,6,2,3},new[]{0,5,6,4,2,3},new[]{0,1,2},new[]{0,1,2,3,4,5,6},new[]{0,1,2,3,5,6}};
    private static readonly (double X1,double Y1,double X2,double Y2)[] Strokes={(0,1,0.6,1),(0.6,1,0.6,0.5),(0.6,0.5,0.6,0),(0,0,0.6,0),(0,0.5,0,0),(0,1,0,0.5),(0,0.5,0.6,0.5)};
    public static Segment3[] Create(Bounds3 b,double height,double offset,int decimals)
    {
        b.Validate();if(!double.IsFinite(height)||!double.IsFinite(offset)||height<=0||offset<height||decimals<0||decimals>6)throw new ArgumentException("字高/偏置/小数位无效");
        var lines=new List<Segment3>();
        void Add(V3 a,V3 c){if(a.Near(c,1e-12))return;if(!a.Finite||!c.Finite)throw new ArgumentException("标注坐标超限");lines.Add(new(a,c));}
        void Dim(V3 a,V3 c,V3 shift,V3 textX,V3 textY,double length){
            if(length<1e-9)return;var p=a+shift;var q=c+shift;var direction=(q-p).Unit();var wing=textY*height*0.25;
            Add(a,p);Add(c,q);Add(p,q);Add(p,p+direction*height*0.5+wing);Add(p,p+direction*height*0.5-wing);Add(q,q-direction*height*0.5+wing);Add(q,q-direction*height*0.5-wing);
            string text=length.ToString("F"+decimals,CultureInfo.InvariantCulture);
            var cursor=(p+q)*0.5-textX*(text.Length*height*0.8/2)+textY*height*0.4;
            foreach(char ch in text){if(ch=='.')Add(cursor,cursor+textX*height*0.1);else foreach(int i in DigitSegments[ch-'0']){var s=Strokes[i];Add(cursor+textX*(s.X1*height)+textY*(s.Y1*height),cursor+textX*(s.X2*height)+textY*(s.Y2*height));}cursor+=textX*height*0.8;}
        }
        var min=b.Min;var max=b.Max;
        Dim(new(min.X,min.Y,max.Z),new(max.X,min.Y,max.Z),new(0,-offset,0),new(1,0,0),new(0,1,0),b.Size.X);
        Dim(new(max.X,min.Y,max.Z),new(max.X,max.Y,max.Z),new(offset,0,0),new(0,1,0),new(-1,0,0),b.Size.Y);
        Dim(new(max.X,max.Y,min.Z),new(max.X,max.Y,max.Z),new(offset*2,0,0),new(0,0,1),new(1,0,0),b.Size.Z);
        if(lines.Count==0)throw new ArgumentException("点状范围没有可标注长度");
        return lines.ToArray();
    }
}
public interface IEditTransaction
{
    bool Active {get;}
    bool Begin();
    void Commit();
    void Cancel();
}
public static class EdgeTopology
{
    // Transient Parasolid edge tags may be rebuilt by an Undo cancellation. A uniquely
    // identifying set of incident persistent face IDs survives a rigid/no-op rollback.
    // Multiple edges between the same faces (including periodic seams) are rejected.
    public static Dictionary<string,int[]> Index(IReadOnlyDictionary<int,int[]> faceEdges)
    {
        if(faceEdges==null||faceEdges.Count==0||faceEdges.Keys.Any(p=>p<=0)||faceEdges.Values.Any(e=>e==null||e.Any(t=>t<=0)))throw new ArgumentException("无效面/边映射");
        return faceEdges.SelectMany(p=>p.Value.Distinct().Select(e=>(Edge:e,Pid:p.Key))).GroupBy(p=>p.Edge)
            .Select(g=>(Tag:g.Key,Key:string.Join(",",g.Select(p=>p.Pid).Distinct().OrderBy(i=>i))))
            .GroupBy(p=>p.Key).ToDictionary(g=>g.Key,g=>g.Select(p=>p.Tag).OrderBy(i=>i).ToArray());
    }
    public static string Capture(int edge,IReadOnlyDictionary<int,int[]> faceEdges)
    {
        var found=Index(faceEdges).Where(p=>p.Value.Contains(edge)).ToArray();
        if(found.Length!=1||found[0].Value.Length!=1)throw new ArgumentException("所选边不属于该实体，或相邻面不能唯一标识这条边");
        return found[0].Key;
    }
    public static int Resolve(string identity,IReadOnlyDictionary<int,int[]> faceEdges)
    {
        var map=Index(faceEdges);
        if(!map.TryGetValue(identity,out var tags)||tags.Length!=1)throw new InvalidOperationException("边拓扑标识失效或不唯一；未扩大选择范围");
        return tags[0];
    }
}
public static class AtomicEdit
{
    public static void Run(IEditTransaction tx,Action mutate,Action verify,Action restoreContext,Action verifyRecovery)
    {
        if(tx.Active)throw new InvalidOperationException("宿主已有活动事务");
        if(!tx.Begin())throw new InvalidOperationException("无法开始撤销事务");
        bool committed=false;
        try{mutate();restoreContext();verify();tx.Commit();committed=true;}
        catch(Exception e){
            var failures=new List<Exception>{e};
            if(!committed){
                try{if(!tx.Active)throw new InvalidOperationException("事务意外结束，无法保证回滚");tx.Cancel();if(tx.Active)throw new InvalidOperationException("回滚后事务仍活动");}catch(Exception ex){failures.Add(ex);}
                try{restoreContext();}catch(Exception ex){failures.Add(ex);}
                try{verifyRecovery();}catch(Exception ex){failures.Add(ex);}
            }
            throw new AggregateException("操作未完成；恢复检查详情："+string.Join("；",failures.Select(x=>x.Message)),failures);
        }
    }
}
