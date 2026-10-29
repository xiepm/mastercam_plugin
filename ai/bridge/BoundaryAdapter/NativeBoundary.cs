using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.IO;
using Mastercam.Math;
using Mastercam.Support;
using Mastercam.Support.Types;
using Mastercam.Database.Types;

namespace MastercamPluginAI.BoundaryAdapter;

public sealed record BoundaryRequest(int SourceId,V3 Origin,double Depth,double Tolerance,int OutputLevel,bool Clockwise);
public sealed record BoundaryReceipt(BoundaryResult Boundary,int[] GeometryIds,Chain[] Chains,bool Committed,string Contract);


/// <summary>Call synchronously on the Mastercam UI thread. No command posting, implicit selection,
/// operation creation, document open/save, global plane changes, or installation entry point.</summary>
public static partial class NativeBoundary
{
    public const string Contract="API29 1.0.5 candidate; EXISTING_VISIBLE_OUTPUT_LEVEL_ONLY; public private single-edge ChainCollection; one selected closed convex planar-faced solid; straight unsplit edges; World-XY CPlane; model units; explicit absolute origin plus signed depth; one outer loop; strict source/inventory/selection/context rollback; new-level engine issue unresolved; native qualification pending";
    public static BoundaryReceipt Preview(BoundaryRequest request)=>Execute(request,false,null);
    public static BoundaryReceipt Create(BoundaryRequest request)=>Execute(request,true,null);
    public static int[] GetExistingVisibleOutputLevels()=>OutputLevelAdmission.Eligible(ContextSeal());
    static void AdmitOutputLevel(int target,string context,string stage)
    {
        try{OutputLevelAdmission.RequireExistingVisible(context,target);}
        catch(Exception e){Record("output-level-admission-refused",new{stage,target,context,error=e.Message},verified:false);throw;}
        Record("output-level-admission-verified",new{stage,target,context,policy="EXISTING_VISIBLE_OUTPUT_LEVEL_ONLY"},verified:true);
    }
    internal static BoundaryReceipt Execute(BoundaryRequest r,bool commit,Action<string> fault)
    {
        audit.Clear();
        BoundaryKernel.Require(r!=null&&r.SourceId>0&&r.OutputLevel>=1&&r.OutputLevel<=999999,"Invalid source or output level.");
        var frame=ProjectionFrame.WorldXY(r.Origin,r.Depth);frame.Validate();
        BoundaryKernel.Require(double.IsFinite(r.Tolerance)&&r.Tolerance>=1e-9&&r.Tolerance<=0.01,"Tolerance outside supported model-unit range.");
        BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"An existing transaction is active; refusing to join or cancel it.");
        RequireWorldXY(ViewManager.CPlane);
        string contextSeal=ContextSeal();
        // Before inventory, face queries (which need selection restoration), extraction or any transaction.
        if(commit)AdmitOutputLevel(r.OutputLevel,contextSeal,"before-source-read");
        var baseline=Capture();var selected=SearchManager.GetSelectedGeometry();
        BoundaryKernel.Require(selected is {Length:1}&&selected[0].GetEntityID()==r.SourceId&&selected[0] is SolidGeometry&&!selected[0].Blanked,
            "Exactly the requested non-blanked solid must already be selected; mixed/extra selections are rejected.");
        var faces=ReadFaces(r.SourceId);
        string faceSeal=JsonSerializer.Serialize(faces);
        BoundaryResult result=RolledBack(baseline,()=>
        {
            fault?.Invoke("before-extraction");
            Record("extraction-input-state",new{provider="ChainCollectionService",state=ExtractionDiagnostics.SelectionState()});
            var geometry=NativeSolidEdges.Read(faces,r.Tolerance,fault);
            VerifyIds(baseline.Keys);VerifyExisting(baseline);VerifyContext(contextSeal);
            Record("body-edge-inventory-unchanged-before-cancel",new{geometryIds=baseline.Keys.Order().ToArray(),edgeCount=geometry.Length},verified:true);
            fault?.Invoke("after-extraction");
            return BoundaryKernel.Project(new(geometry,faces),frame,r.Tolerance,r.Clockwise);
        });
        audit.Add(new("private-body-edge-extraction-restoration-verified",Array.Empty<int>(),true,"Private wrappers disposed; no database wireframe generated; original inventory, selection, stamps and context verified before and after cancellation."));
        BoundaryKernel.Require(JsonSerializer.Serialize(ReadFaces(r.SourceId))==faceSeal,"Source topology/normal changed after extraction rollback.");
        VerifyContext(contextSeal);
        if(!commit)return new(result,Array.Empty<int>(),Array.Empty<Chain>(),false,Contract);
        RequireWorldXY(ViewManager.CPlane);
        // Recheck live context after private edge extraction; never rely on a UI/preview cache.
        AdmitOutputLevel(r.OutputLevel,ContextSeal(),"before-output-transaction");
        var outputLevel=new NativeOutputLevelLease(r.OutputLevel,contextSeal);
        bool owns=false;
        try
        {
            BoundaryKernel.Require(UndoManager.StartTransaction(),"Output transaction could not start.");owns=true;
            var output=new List<Geometry>();
            for(int i=0;i<result.WorldPoints.Length;i++)
            {
                var line=new LineGeometry(P(result.WorldPoints[i]),P(result.WorldPoints[(i+1)%result.WorldPoints.Length]))
                    {Level=r.OutputLevel,Selected=false};
                if(i==0)outputLevel.Observe("after-line-construction-before-Commit");
                outputLevel.MarkCreationAttempt();
                BoundaryKernel.Require(line.Commit(),"Output line commit failed.");output.Add(line);
                outputLevel.Observe("after-output-line-Commit-"+i);
                fault?.Invoke("after-output-line");
            }
            var ids=output.Select(g=>g.GetEntityID()).ToArray();
            BoundaryKernel.Require(ids.All(i=>i>0&&!baseline.ContainsKey(i))&&ids.Distinct().Count()==ids.Length,"Invalid output IDs.");
            var chains=ChainManager.ChainGeometry(output.ToArray());
            BoundaryKernel.Require(chains is {Length:1},"Expected exactly one outer boundary chain.");
            var chain=chains[0];
            BoundaryKernel.Require(chain.View==ViewManager.CPlane.ViewNumber,"Chain view does not match the verified World-XY CPlane.");
            chain.Direction=r.Clockwise?ChainDirectionType.Clockwise:ChainDirectionType.CounterClockwise;
            BoundaryKernel.Require(chain.IsClosed&&chain.IsFlat&&!chain.ContainsSplines&&chain.CurvesCount==ids.Length,"Incomplete/non-planar output chain.");
            double nativeDepth=ViewManager.ConvertToViewCoordinates(P(result.WorldPoints[0]),ViewManager.CPlane).z;
            BoundaryKernel.Require(Math.Abs(chain.Depth-nativeDepth)<=r.Tolerance,"Chain depth does not match explicit world point transformed through the active CPlane origin.");
            BoundaryKernel.Require(chain.Direction==(r.Clockwise?ChainDirectionType.Clockwise:ChainDirectionType.CounterClockwise),"Chain direction readback mismatch.");
            var chained=ChainManager.GetGeometryInChain(chain);
            BoundaryKernel.Require(chained!=null&&chained.Length==ids.Length&&chained.Select(g=>g.GetEntityID()).Order().SequenceEqual(ids.Order()),"Chain membership mismatch.");
            BoundaryKernel.Require(Math.Abs(Math.Abs(chain.Area)-Math.Abs(result.SignedArea))<=r.Tolerance*result.Perimeter*4&&
                Math.Abs(chain.Perimeter-result.Perimeter)<=r.Tolerance*ids.Length*4,"Chain area/perimeter mismatch.");
            foreach(var g in output)
            {
                BoundaryKernel.Require(g.Retrieve()&&g is LineGeometry,"Output readback failed.");
                var line=(LineGeometry)g;int i=output.IndexOf(g);
                BoundaryKernel.Require((V(line.EndPoint1)-result.WorldPoints[i]).Length<=r.Tolerance&&
                    (V(line.EndPoint2)-result.WorldPoints[(i+1)%ids.Length]).Length<=r.Tolerance&&line.Level==r.OutputLevel,"Output coordinate/level mismatch.");
            }
            RestoreSelection(baseline);
            VerifyExisting(baseline);VerifyIds(baseline.Keys.Concat(ids));
            BoundaryKernel.Require(JsonSerializer.Serialize(ReadFaces(r.SourceId))==faceSeal,"Source face contract changed.");
            outputLevel.PrepareCommit();
            VerifyExisting(baseline);VerifyIds(baseline.Keys.Concat(ids));
            fault?.Invoke("before-output-commit");
            UndoManager.CommitTransaction();
            BoundaryKernel.Require(!UndoManager.IsTransactionActive(),"Output transaction remained active.");owns=false;
            audit.Add(new("output-committed",ids,true,"Complete chain, coordinates, source seal and baseline read back before commit."));
            return new(result,ids,chains,true,Contract);
        }
        catch(Exception original)
        {
            if(owns)
            {
                try{CancelAndVerify(baseline,contextSeal,outputLevel:outputLevel);}catch(Exception rollback){throw new AggregateException("Output failed and rollback verification failed; manual inspection required.",original,rollback);}
            }
            throw;
        }
    }
    internal static FaceEvidence[] ReadFaces(int sourceId)
    {
        var before=Capture();
        BoundaryKernel.Require(Inventory().Any(g=>g.GetEntityID()==sourceId&&g is SolidGeometry),"Source is not an alive solid body.");
        Dictionary<int,int> map=null;int[] selectionBefore=ExtractionDiagnostics.SelectedIds();
        try
        {
            // API29 IL 0x06002411 clears selected bit 4 with add_undo=false before returning faces.
            // This query is NOT read-only with respect to selection. Preserve it explicitly, even on error.
            map=SearchManager.GetFaceTagsAndPidMapFromBodyEntity(sourceId);
            Record("face-map-query-selection",new{sourceId,before=selectionBefore,afterRawCall=ExtractionDiagnostics.SelectedIds(),faceCount=map?.Count});
        }
        finally
        {
            RestoreSelection(before);VerifyIds(before.Keys);VerifyExisting(before);
            Record("face-map-selection-restored",new{sourceId,selected=ExtractionDiagnostics.SelectedIds()},verified:true);
        }
        BoundaryKernel.Require(map is {Count:>=1 and <=1024}&&map.Values.Distinct().Count()==map.Count,"Invalid/incomplete face map.");
        foreach(int tag in map.Values)
        {
            var result=SearchManager.GetFaceTypeAndParameters(tag);
            BoundaryKernel.Require(result?.ResultType is ResultType kind&&kind==ResultType.Plane,"Only true planar faces are supported; curved/unknown faces rejected.");
        }
        BoundaryKernel.Require(map.Count>=4,"Too few planar faces for a closed volume.");
        return map.OrderBy(k=>k.Key).Select(k=>
        {
            var tags=SearchManager.GetEdgeTagsFromFace(k.Value);
            BoundaryKernel.Require(tags is {Length:>=3},"Face edge lookup failed.");
            return new FaceEvidence(k.Key,V(SearchManager.GetFaceNormal(k.Value)),tags.Order().ToArray());
        }).ToArray();
    }
    static T RolledBack<T>(Dictionary<int,Stamp> baseline,Func<T> work,Func<IEnumerable<int>> observedReturnedIds=null)
    {
        string context=ContextSeal();
        BoundaryKernel.Require(UndoManager.StartTransaction(),"Extraction transaction could not start.");
        T value=default;Exception original=null;
        try{value=work();}catch(Exception e){original=e;}
        try{CancelAndVerify(baseline,context,observedReturnedIds?.Invoke());}catch(Exception e){throw new AggregateException("Extraction rollback was not verified.",original==null?new[]{e}:new[]{original,e});}
        if(original!=null)System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(original).Throw();
        return value;
    }
    internal static void RequireWorldXY(MCView view)
    {
        BoundaryKernel.Require(view!=null,"Missing chain/CPlane view.");var m=view.ViewMatrix;
        BoundaryKernel.Require((V(m.Row1)-new V3(1,0,0)).Length<1e-10&&(V(m.Row2)-new V3(0,1,0)).Length<1e-10&&
            (V(m.Row3)-new V3(0,0,1)).Length<1e-10,"Native v1 requires a World-XY oriented CPlane/chain view; no plane is changed.");
    }

}
