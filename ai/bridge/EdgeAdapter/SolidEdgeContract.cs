using System;
using System.Linq;

namespace MastercamPluginAI.EdgeAdapter;

public sealed record EdgePointEvidence(int Dimension,double[] Coordinates);
public sealed record SolidEdgeChainEvidence(int ChainId,bool IsLinear,bool IsClosed,double Length,int[] UsedEdgeTags,EdgePointEvidence[][] Streams);
public sealed record SolidEdgeEvidence(int RequestedEdgeTag,SolidEdgeChainEvidence[] Chains);

/// <summary>Validate the observed public single-edge contract before treating two points as an exact line.</summary>
public static class SolidEdgeContract
{
    public static Edge3 Validate(SolidEdgeEvidence evidence,double tolerance)
    {
        BoundaryKernel.Require(double.IsFinite(tolerance)&&tolerance>=1e-9&&tolerance<=0.01,"Invalid edge tolerance.");
        BoundaryKernel.Require(evidence!=null&&evidence.RequestedEdgeTag>0,"Invalid requested edge tag.");
        BoundaryKernel.Require(evidence.Chains is {Length:1}&&evidence.Chains[0]!=null,"Expected exactly one non-null edge chain.");
        var c=evidence.Chains[0];
        BoundaryKernel.Require(c.ChainId>0&&c.IsLinear&&!c.IsClosed,"Edge chain must be linear, open, and have a positive private chain ID.");
        BoundaryKernel.Require(c.UsedEdgeTags is {Length:1}&&c.UsedEdgeTags[0]==evidence.RequestedEdgeTag,"Chain edge tag does not exactly match requested tag.");
        BoundaryKernel.Require(c.Streams is {Length:1}&&c.Streams[0] is {Length:2},"Edge chain must return one stream with exactly two endpoints.");
        V3 Point(EdgePointEvidence p)
        {
            BoundaryKernel.Require(p!=null&&p.Dimension==3&&p.Coordinates is {Length:3},"Endpoint must contain exactly three coordinates and dimension 3.");
            var v=new V3(p.Coordinates[0],p.Coordinates[1],p.Coordinates[2]);
            BoundaryKernel.Require(v.Finite&&p.Coordinates.All(x=>Math.Abs(x)<=1e8),"Non-finite or unsupported endpoint coordinate.");return v;
        }
        var a=Point(c.Streams[0][0]);var b=Point(c.Streams[0][1]);double distance=(b-a).Length;
        BoundaryKernel.Require(double.IsFinite(c.Length)&&c.Length>32*tolerance&&distance>32*tolerance,"Degenerate or tolerance-sized edge length.");
        BoundaryKernel.Require(Math.Abs(c.Length-distance)<=tolerance,"Native chain length differs from endpoint distance.");
        return new(a,b,evidence.RequestedEdgeTag);
    }
}
