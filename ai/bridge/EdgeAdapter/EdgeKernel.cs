using System;
using System.Collections.Generic;
using System.Linq;
namespace MastercamPluginAI.EdgeAdapter;

public readonly record struct V3(double X,double Y,double Z)
{
    public static V3 operator +(V3 a,V3 b)=>new(a.X+b.X,a.Y+b.Y,a.Z+b.Z);
    public static V3 operator -(V3 a,V3 b)=>new(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
    public double Length=>Math.Sqrt(X*X+Y*Y+Z*Z);
    public bool Finite=>double.IsFinite(X)&&double.IsFinite(Y)&&double.IsFinite(Z);
}
public sealed record Edge3(V3 A,V3 B,int Tag=0);
public sealed record FaceEvidence(int PersistentId,V3 OutwardNormal,int[] EdgeTags);
internal static class BoundaryKernel
{
    internal static void Require(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
}
public enum EdgeMode{Edges3D,ProjectWorldXY}
public sealed record EdgeRequest(int SourceId,EdgeMode Mode,int OutputLevel,double OutputZ=0,double Tolerance=0.0001,int Color=10);
public sealed record OutputSegment(V3 A,V3 B,int[] SourceTags);
public sealed record EdgeGeometry(Edge3[] SourceEdges,OutputSegment[] Segments,int[] CollapsedTags,int MergedDuplicates);
/// <summary>Original exact straight-edge output and orthographic WorldXY projection.
/// No hull, silhouette, hidden-line removal, sampling/fitting, or partial-overlap union.</summary>
public static class EdgeKernel
{
    public static EdgeGeometry Plan(Edge3[] edges,EdgeMode mode,double z,double tolerance)
    {
        BoundaryKernel.Require(Enum.IsDefined(mode)&&double.IsFinite(z)&&Math.Abs(z)<=1e8,"无效输出模式或世界Z。");
        BoundaryKernel.Require(double.IsFinite(tolerance)&&tolerance>=1e-9&&tolerance<=0.01,"公差须为1e-9至0.01模型单位。");
        BoundaryKernel.Require(edges is {Length:>=1 and <=4096}&&edges.All(e=>e!=null&&e.Tag>0)&&edges.Select(e=>e.Tag).Distinct().Count()==edges.Length,"源边为空、重复或超过4096条。");
        var output=new List<OutputSegment>();var collapsed=new List<int>();int merged=0;
        foreach(var edge in edges.OrderBy(e=>e.Tag))
        {
            BoundaryKernel.Require(edge.A.Finite&&edge.B.Finite&&new[]{edge.A.X,edge.A.Y,edge.A.Z,edge.B.X,edge.B.Y,edge.B.Z}.All(v=>Math.Abs(v)<=1e8)&&(edge.A-edge.B).Length>32*tolerance,"源边坐标或长度不支持。");
            var a=mode==EdgeMode.Edges3D?edge.A:new V3(edge.A.X,edge.A.Y,z);
            var b=mode==EdgeMode.Edges3D?edge.B:new V3(edge.B.X,edge.B.Y,z);
            if(mode==EdgeMode.ProjectWorldXY&&(a-b).Length<=tolerance){collapsed.Add(edge.Tag);continue;}
            BoundaryKernel.Require((a-b).Length>32*tolerance,"投影产生过短线段；请降低公差或选择其他投影。");
            int duplicate=mode==EdgeMode.Edges3D?-1:output.FindIndex(s=>((s.A-a).Length<=tolerance&&(s.B-b).Length<=tolerance)||((s.A-b).Length<=tolerance&&(s.B-a).Length<=tolerance));
            if(duplicate>=0){var old=output[duplicate];output[duplicate]=old with{SourceTags=old.SourceTags.Append(edge.Tag).ToArray()};merged++;}
            else output.Add(new(a,b,new[]{edge.Tag}));
        }
        BoundaryKernel.Require(output.Count>0,"投影后无有效直线输出。");
        return new(edges.OrderBy(e=>e.Tag).ToArray(),output.ToArray(),collapsed.ToArray(),merged);
    }
}
