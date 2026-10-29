using System;
using System.Collections.Generic;
using System.Linq;
using Mastercam.Chaining;
using Mastercam.Chaining.Types;

namespace MastercamPluginAI.BoundaryAdapter;

/// <summary>Public API29 path observed in round2 P07. Each actual body edge owns a private collection.
/// No database wireframe creation, display context, Repaint, operation binding, or legacy fallback.</summary>
internal static class NativeSolidEdges
{
    internal static Edge3[] Read(FaceEvidence[] faces,double tolerance,Action<string> fault)
    {
        BoundaryKernel.Require(faces is {Length:>=4 and <=1024},"Invalid bounded face topology.");
        BoundaryKernel.Require(faces.All(f=>f!=null&&f.EdgeTags is {Length:>=3}&&f.EdgeTags.All(t=>t>0)&&f.EdgeTags.Distinct().Count()==f.EdgeTags.Length),"Invalid face edge tags.");
        var topology=faces.SelectMany(f=>f.EdgeTags).GroupBy(t=>t).OrderBy(g=>g.Key).ToArray();
        BoundaryKernel.Require(topology.Length>=6&&topology.Length<=4096&&topology.All(g=>g.Count()==2),"Each bounded body edge must belong to exactly two faces.");
        var edges=new List<Edge3>();
        foreach(var tag in topology)edges.Add(ReadOne(tag.Key,tolerance,fault));
        BoundaryKernel.Require(edges.Select(e=>e.Tag).SequenceEqual(topology.Select(g=>g.Key)),"Incomplete/duplicate edge-tag extraction.");
        NativeBoundary.Record("body-edge-extraction-complete",new{provider="ChainCollectionService",edgeTags=edges.Select(e=>e.Tag).ToArray(),edgeCount=edges.Count,
            databaseWireframeCreationRequested=false,explicitRepaintCalled=false},verified:true);
        return edges.ToArray();
    }
    static Edge3 ReadOne(int tag,double tolerance,Action<string> fault)
    {
        var owned=new List<IDisposable>();Exception original=null;
        try
        {
            var service=new ChainCollectionService();owned.Add(service);
            var use=new ChainUse(ChainUseType.Curves,0);owned.Add(use);
            var process=service.LoadProcessContext(use);if(process!=null)owned.Add(process);
            BoundaryKernel.Require(process!=null&&process.IsConnected(),"Private body-edge process context is not connected.");
            process.AddSolidEdgeChainSingle(tag,0.5);
            var containers=service.GetChainContainers(use);
            if(containers!=null)foreach(var item in containers)if(item!=null)owned.Add(item);
            NativeBoundary.Record("body-edge-container-count",new{requestedEdgeTag=tag,isNull=containers==null,count=containers?.Count});
            BoundaryKernel.Require(containers is {Count:1}&&containers[0]!=null,"Expected one non-null private body-edge chain.");
            var chain=containers[0];int id=chain.GetId();bool linear=chain.GetIsLinear(),closed=chain.GetIsClosed();
            double length=chain.GetLength();var used=service.CalculateUsedSolidEdgeTags(id)?.ToArray();
            NativeBoundary.Record("body-edge-chain-facts",new{requestedEdgeTag=tag,chainId=id,isLinear=linear,isClosed=closed,length,usedEdgeTags=used});
            BoundaryKernel.Require(id>0&&linear&&!closed,"Private body-edge chain must be linear and open.");
            BoundaryKernel.Require(used is {Length:1}&&used[0]==tag,"Private chain did not return the exact requested edge tag.");
            var streams=service.CalculatePolylinePoints3D(id,tolerance);
            NativeBoundary.Record("body-edge-stream-counts",new{requestedEdgeTag=tag,isNull=streams==null,count=streams?.Count,pointCounts=streams?.Select(s=>(int?)s?.Count).ToArray()});
            BoundaryKernel.Require(streams is {Count:1}&&streams[0] is {Count:2},"Private linear edge requires exactly one two-point stream.");
            var points=streams[0].Select(p=>p==null?null:new EdgePointEvidence(p.Dim,p.GetData())).ToArray();
            var evidence=new SolidEdgeEvidence(tag,new[]{new SolidEdgeChainEvidence(id,linear,closed,length,used,new[]{points})});
            NativeBoundary.Record("body-edge-endpoint-evidence",evidence);
            var edge=SolidEdgeContract.Validate(evidence,tolerance);
            NativeBoundary.Record("body-edge-length-verified",new{tag,nativeLength=length,endpointDistance=(edge.B-edge.A).Length,tolerance},verified:true);
            fault?.Invoke("after-body-edge-read");
            return edge;
        }
        catch(Exception e){original=e;throw;}
        finally
        {
            var errors=new List<Exception>();
            // Dispose every acquired wrapper, even if validation or another Dispose throws.
            for(int i=owned.Count-1;i>=0;i--)try{owned[i].Dispose();}catch(Exception e){errors.Add(e);}
            NativeBoundary.Record("body-edge-resources-disposed",new{tag,ownedWrappers=owned.Count,disposeErrorCount=errors.Count},verified:errors.Count==0);
            if(errors.Count>0)throw new AggregateException("Body-edge wrapper disposal failed.",original==null?errors:new[]{original}.Concat(errors));
        }
    }
}
