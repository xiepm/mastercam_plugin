using System;
using System.Collections.Generic;
using System.Linq;

namespace MastercamPluginAI.BoundaryAdapter;

public readonly record struct V3(double X, double Y, double Z)
{
    public static V3 operator +(V3 a,V3 b)=>new(a.X+b.X,a.Y+b.Y,a.Z+b.Z);
    public static V3 operator -(V3 a,V3 b)=>new(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
    public static V3 operator *(V3 a,double s)=>new(a.X*s,a.Y*s,a.Z*s);
    public double Dot(V3 b)=>X*b.X+Y*b.Y+Z*b.Z;
    public V3 Cross(V3 b)=>new(Y*b.Z-Z*b.Y,Z*b.X-X*b.Z,X*b.Y-Y*b.X);
    public double Length=>Math.Sqrt(Dot(this));
    public bool Finite=>double.IsFinite(X)&&double.IsFinite(Y)&&double.IsFinite(Z);
}
public readonly record struct V2(double X,double Y)
{
    public static V2 operator -(V2 a,V2 b)=>new(a.X-b.X,a.Y-b.Y);
    public double Cross(V2 b)=>X*b.Y-Y*b.X;
    public double Length=>Math.Sqrt(X*X+Y*Y);
}
public sealed record ProjectionFrame(V3 Origin,V3 U,V3 V,V3 N,double Depth)
{
    public void Validate()
    {
        BoundaryKernel.Require(Origin.Finite&&U.Finite&&V.Finite&&N.Finite&&double.IsFinite(Depth),"Non-finite frame.");
        BoundaryKernel.Require(Math.Max(Math.Abs(Origin.X),Math.Max(Math.Abs(Origin.Y),Math.Abs(Origin.Z)))<=1e8&&Math.Abs(Depth)<=1e8,"Unsupported frame magnitude.");
        BoundaryKernel.Require(Math.Abs(U.Length-1)<1e-10&&Math.Abs(V.Length-1)<1e-10&&Math.Abs(N.Length-1)<1e-10&&
            Math.Abs(U.Dot(V))<1e-10&&(U.Cross(V)-N).Length<1e-10,"Frame must be orthonormal and right-handed.");
    }
    public V2 Project(V3 p)=>new((p-Origin).Dot(U),(p-Origin).Dot(V));
    public V3 Lift(V2 p)=>Origin+U*p.X+V*p.Y+N*Depth;
    public static ProjectionFrame WorldXY(V3 origin,double depth)=>new(origin,new(1,0,0),new(0,1,0),new(0,0,1),depth);
}
public sealed record Edge3(V3 A,V3 B,int Tag=0);
public sealed record FaceEvidence(int PersistentId,V3 OutwardNormal,int[] EdgeTags);
public sealed record PolyhedronEvidence(Edge3[] Edges,FaceEvidence[] Faces);
public sealed record BoundaryResult(V2[] PlanePoints,V3[] WorldPoints,double SignedArea,double Perimeter,
    double Volume,int VertexCount,int EdgeCount,int FaceCount,bool Clockwise);

/// <summary>Original bounded algorithm: certify a convex planar B-rep edge graph, then project its vertices.
/// A hull without this certificate is never accepted as a solid silhouette.</summary>
public static class BoundaryKernel
{
    public static void Require(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
    public static BoundaryResult Project(PolyhedronEvidence input,ProjectionFrame frame,double tolerance,bool clockwise)
    {
        frame.Validate();
        Require(double.IsFinite(tolerance)&&tolerance>=1e-9&&tolerance<=0.01,"Tolerance outside supported model-unit range.");
        Require(input?.Edges is {Length:>=6 and <=4096}&&input.Faces is {Length:>=4 and <=1024},"Unsupported or empty polyhedron.");
        var vertices=new List<V3>();
        int Vertex(V3 p)
        {
            Require(p.Finite&&Math.Max(Math.Abs(p.X),Math.Max(Math.Abs(p.Y),Math.Abs(p.Z)))<=1e8,"Unsupported coordinate magnitude.");
            var matches=Enumerable.Range(0,vertices.Count).Where(i=>(vertices[i]-p).Length<=tolerance).ToArray();
            Require(matches.Length<=1,"Ambiguous endpoint weld.");
            if(matches.Length==1)return matches[0];
            vertices.Add(p);return vertices.Count-1;
        }
        var edges=input.Edges.Select(e=>(A:Vertex(e.A),B:Vertex(e.B))).ToArray();
        Require(vertices.Count>=4,"Insufficient vertices.");
        var keys=new HashSet<(int,int)>();
        foreach(var e in edges)
        {
            Require(e.A!=e.B&&(vertices[e.A]-vertices[e.B]).Length>32*tolerance,"Degenerate or tolerance-sized edge.");
            Require(keys.Add(Pair(e.A,e.B)),"Duplicate edge.");
        }
        var faces=input.Faces;
        Require(faces.Select(f=>f.PersistentId).Distinct().Count()==faces.Length,"Duplicate face identity.");
        var tags=new Dictionary<int,List<int>>();
        for(int f=0;f<faces.Length;f++)
        {
            var face=faces[f];
            Require(face.OutwardNormal.Finite&&Math.Abs(face.OutwardNormal.Length-1)<1e-6,"Invalid outward face normal.");
            Require(face.EdgeTags is {Length:>=3}&&face.EdgeTags.Distinct().Count()==face.EdgeTags.Length&&face.EdgeTags.All(t=>t>0),"Invalid face edges.");
            foreach(int tag in face.EdgeTags){if(!tags.ContainsKey(tag))tags[tag]=new();tags[tag].Add(f);}
            for(int j=0;j<f;j++)Require((face.OutwardNormal-faces[j].OutwardNormal).Length>1e-7,"Parallel coplanar splits or concave steps are unsupported.");
        }
        Require(tags.Count==edges.Length&&tags.Values.All(v=>v.Count==2),"Incomplete edges or non-manifold source topology.");
        bool tagged=input.Edges.Any(e=>e.Tag!=0);
        if(tagged)Require(input.Edges.All(e=>e.Tag>0)&&input.Edges.Select(e=>e.Tag).Distinct().Count()==edges.Length&&
            input.Edges.Select(e=>e.Tag).Order().SequenceEqual(tags.Keys.Order()),"Extracted edge tags do not match complete face topology.");
        var expectedPairs=tags.Values.Select(v=>Pair(v[0],v[1])).ToArray();
        Require(expectedPairs.Distinct().Count()==edges.Length,"Multiple edges between the same faces are unsupported.");
        var anchor=vertices[0];
        var normals=faces.Select(f=>f.OutwardNormal*(1/f.OutwardNormal.Length)).ToArray();
        var offsets=normals.Select(n=>vertices.Max(v=>(v-anchor).Dot(n))).ToArray();
        var faceEdges=Enumerable.Range(0,faces.Length).Select(_=>new List<int>()).ToArray();
        var actualPairs=new HashSet<(int,int)>();
        for(int i=0;i<edges.Length;i++)
        {
            var e=edges[i];
            var supports=Enumerable.Range(0,faces.Length).Where(f=>
                Math.Abs((vertices[e.A]-anchor).Dot(normals[f])-offsets[f])<=tolerance&&
                Math.Abs((vertices[e.B]-anchor).Dot(normals[f])-offsets[f])<=tolerance).ToArray();
            Require(supports.Length==2,"Edge is not on exactly two convex supporting planes; reject concavity/interior edges.");
            if(tagged)Require(supports.Order().SequenceEqual(tags[input.Edges[i].Tag].Order()),"Edge tag is bound to geometry on different faces.");
            Require(actualPairs.Add(Pair(supports[0],supports[1])),"Duplicate support edge.");
            foreach(int f in supports)faceEdges[f].Add(i);
        }
        Require(actualPairs.SetEquals(expectedPairs),"Face adjacency does not match the complete extracted geometry.");
        Require(vertices.Count-edges.Length+faces.Length==2,"Closed convex Euler certificate failed.");
        var graph=Enumerable.Range(0,vertices.Count).Select(_=>new List<int>()).ToArray();
        foreach(var e in edges){graph[e.A].Add(e.B);graph[e.B].Add(e.A);}
        Require(graph.All(g=>g.Count>=3),"Open or split vertex topology.");
        Require(Connected(graph,0)==vertices.Count,"Disconnected source.");
        var center=vertices.Aggregate(new V3(),(a,b)=>a+b)*(1.0/vertices.Count);
        double volume=0,surfaceArea=0;
        for(int f=0;f<faces.Length;f++)
        {
            Require(faceEdges[f].Count==faces[f].EdgeTags.Length,"Incomplete face boundary.");
            var adjacency=new Dictionary<int,List<int>>();
            foreach(int i in faceEdges[f]){var e=edges[i];Add(e.A,e.B);Add(e.B,e.A);}
            void Add(int a,int b){if(!adjacency.ContainsKey(a))adjacency[a]=new();adjacency[a].Add(b);}
            Require(adjacency.Values.All(v=>v.Count==2),"Face boundary is branched/open.");
            int first=adjacency.Keys.Min(),previous=-1,current=first;
            var loop=new List<int>();
            do
            {
                Require(!loop.Contains(current),"Self-intersecting face topology.");loop.Add(current);
                var next=adjacency[current].First(v=>v!=previous);previous=current;current=next;
            }while(current!=first);
            Require(loop.Count==adjacency.Count,"Face has holes/disconnected loops.");
            var areaVector=new V3();
            for(int i=1;i<loop.Count-1;i++)areaVector+=(vertices[loop[i]]-vertices[loop[0]]).Cross(vertices[loop[i+1]]-vertices[loop[0]]);
            if(areaVector.Dot(normals[f])<0)loop.Reverse();
            for(int i=0;i<loop.Count;i++)
            {
                var a=vertices[loop[i]];var b=vertices[loop[(i+1)%loop.Count]];
                foreach(int v in loop)Require((b-a).Cross(vertices[v]-a).Dot(normals[f])>=-tolerance*(b-a).Length,"Non-convex/self-intersecting face.");
            }
            for(int i=1;i<loop.Count-1;i++)
            {
                var a=vertices[loop[0]]-center;var b=vertices[loop[i]]-center;var c=vertices[loop[i+1]]-center;
                volume+=a.Dot(b.Cross(c))/6;surfaceArea+=(b-a).Cross(c-a).Length/2;
            }
        }
        Require(double.IsFinite(volume)&&volume>surfaceArea*tolerance*8,"Zero/thin volume or inward topology.");
        var projected=vertices.Select(frame.Project).OrderBy(p=>p.X).ThenBy(p=>p.Y).ToArray();
        var points=new List<V2>();
        foreach(var p in projected)if(!points.Any(q=>(p-q).Length<=tolerance))points.Add(p);
        var hull=Hull(points);
        Require(hull.Length>=3,"Projection collapsed.");
        if(clockwise)Array.Reverse(hull);
        int start=Enumerable.Range(0,hull.Length).OrderBy(i=>hull[i].X).ThenBy(i=>hull[i].Y).First();
        hull=Enumerable.Range(0,hull.Length).Select(i=>hull[(i+start)%hull.Length]).ToArray();
        double area=SignedArea(hull),perimeter=0;
        for(int i=0;i<hull.Length;i++)
        {
            double length=(hull[(i+1)%hull.Length]-hull[i]).Length;
            Require(length>32*tolerance,"Projection has tolerance-sized edges.");perimeter+=length;
        }
        Require(Math.Abs(area)>perimeter*tolerance*8,"Projection is too thin.");
        foreach(var p in projected)for(int i=0;i<hull.Length;i++)
        {
            var edge=hull[(i+1)%hull.Length]-hull[i];double cross=edge.Cross(p-hull[i])*(clockwise?-1:1);
            Require(cross>=-tolerance*edge.Length,"Projection lost a source vertex.");
        }
        return new(hull,hull.Select(frame.Lift).ToArray(),area,perimeter,volume,vertices.Count,edges.Length,faces.Length,clockwise);
    }
    static (int,int) Pair(int a,int b)=>a<b?(a,b):(b,a);
    static int Connected(List<int>[] graph,int start)
    {var seen=new HashSet<int>();var todo=new Stack<int>();todo.Push(start);while(todo.Count>0){int i=todo.Pop();if(!seen.Add(i))continue;foreach(int j in graph[i])todo.Push(j);}return seen.Count;}
    static V2[] Hull(List<V2> p)
    {
        var lower=new List<V2>();var upper=new List<V2>();
        void Append(List<V2> h,V2 q){while(h.Count>=2&&(h[^1]-h[^2]).Cross(q-h[^1])<=0)h.RemoveAt(h.Count-1);h.Add(q);}
        foreach(var q in p)Append(lower,q);for(int i=p.Count-1;i>=0;i--)Append(upper,p[i]);
        if(lower.Count>0)lower.RemoveAt(lower.Count-1);if(upper.Count>0)upper.RemoveAt(upper.Count-1);return lower.Concat(upper).ToArray();
    }
    public static double SignedArea(IReadOnlyList<V2> p)
    {if(p.Count<3)return 0;double sum=0;for(int i=1;i<p.Count-1;i++)sum+=(p[i]-p[0]).Cross(p[i+1]-p[0]);return sum/2;}
}
