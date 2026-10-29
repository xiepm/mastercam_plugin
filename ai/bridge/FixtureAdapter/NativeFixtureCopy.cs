using System;
using System.Linq;
using FixtureTools2027.Core;

namespace MastercamPluginAI.FixtureAdapter;

// Retained public diagnostic signatures for the parent's earlier harness.
public sealed record NativeCopyObservation(int SourceId,int TemporaryCopyId,string Type,string ReadbackCoverage,bool ExtentsVerified);
public sealed record NativeCopyProbeReport(string Status,NativeCopyObservation[] Copies,string[] Diagnostics,bool RequiresHostReview);

public static class NativeFixtureCopy
{
    public static NativeFixtureSession OpenSession()=>new(new NativeGeometryHost());
    /// <summary>Production native geometry placement. Create, measure/read back and commit in one host-thread callback.</summary>
    public static NativePlacementReport PlaceSelected(Vec3 reference,Vec3 target,Vec3 translation,double worldZDegrees)
    {using var session=OpenSession();return session.ApplySelected(reference,target,translation,worldZDegrees);}
    public static NativeCopyProbeReport ProbeSelected(Vec3 reference,Vec3 target,Vec3 translation,double worldZDegrees)
    {
        using var session=OpenSession();session.StageSelected(reference,target,translation,worldZDegrees);var report=session.Cancel();
        return new(report.Status=="rolled-back"?"probe-rolled-back":"probe-outcome-uncertain",report.Copies.Select(c=>new NativeCopyObservation(c.SourceId,c.CopyId,c.CopyType,
            "Per-entity world AABB, semantic family, attributes/styles and available endpoint samples; no B-rep equality claim.",c.ExtentsVerified)).ToArray(),report.Diagnostics,report.RequiresHostReview);
    }
}
