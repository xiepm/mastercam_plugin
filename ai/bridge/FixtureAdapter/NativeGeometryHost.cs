using System;
using System.Collections.Generic;
using System.Linq;
using FixtureTools2027.Core;
using Mastercam.BasicGeometry;
using Mastercam.Curves;
using Mastercam.Database;
using Mastercam.GeometryUtility;
using Mastercam.GeometryUtility.Types;
using Mastercam.IO;
using Mastercam.Math;

namespace MastercamPluginAI.FixtureAdapter;

/// <summary>Locally adapted from the user-owned GeometryTools2027 measurement pattern. No runtime suite dependency.</summary>
internal sealed class NativeGeometryHost : INativeFixtureHost
{
    private readonly Api29Host host=new();
    private NativeViewState? context;
    public void CaptureContext(){AssertHostThread();context=new NativeViewState();}
    public void RestoreContext(){AssertHostThread();context?.Restore();}
    public void VerifyContext(){AssertHostThread();context?.Verify();}
    public void AssertHostThread()=>host.AssertHostThread();
    public DocumentStamp Document=>host.Document;
    public bool TransactionActive=>host.TransactionActive;
    public bool StartTransaction()=>host.StartTransaction();
    public void CommitTransaction()=>host.CommitTransaction();
    public void CancelTransaction()=>host.CancelTransaction();
    public string[] BoundaryDiagnostics=>host.BoundaryDiagnostics;
    private static Vec3 V(Point3D p)=>new(p.x,p.y,p.z);
    private static Point3D P(Vec3 p)=>new(p.X,p.Y,p.Z);
    internal static Geometry Get(int id)
    {var g=Geometry.RetrieveEntity(id);if(g==null||!g.Retrieve()||g.GetEntityID()!=id)throw new FixtureException("Unable to retrieve native entity "+id);return g;}
    private static string Family(Geometry g)=>g is SolidGeometry?"solid":g is CurveGeometry?"curve":g is PointGeometry?"point":"unsupported";
    public NativeEntityState[] ReadDocument()
    {
        AssertHostThread();return host.ReadDocument().Select(r=>
        {
            var g=Get(r.Id);
            Vec3[] samples=g is PointGeometry p?new[]{V(p.Data)}:g is LineGeometry l?new[]{V(l.EndPoint1),V(l.EndPoint2)}:g is CurveGeometry c?new[]{V(c.EndPoint1),V(c.EndPoint2)}:Array.Empty<Vec3>();
            foreach(var sample in samples)sample.Validate("Native sample");
            return new NativeEntityState(r.Id,r.Type,Family(g),r.Level,r.Color,r.Selected,r.Blanked,
                FormattableString.Invariant($"{g.LineStyle}|{g.LineWidth:R}|{g.PenStyle}|{g.PointStyle}"),samples);
        }).OrderBy(s=>s.Id).ToArray();
    }
    public void ValidateSource(int id)
    {
        AssertHostThread();var g=Get(id);
        if(Family(g)=="unsupported"||!g.Validate())throw new FixtureException("Unsupported native fixture geometry: "+g.GetType().FullName);
        if(!LevelsManager.IsLevelVisible(g.Level))throw new FixtureException("Native fixture source level must already be visible: "+g.Level);
    }
    private static bool Close(Vec3 a,Vec3 b)=>Math.Abs(a.X-b.X)<1e-10&&Math.Abs(a.Y-b.Y)<1e-10&&Math.Abs(a.Z-b.Z)<1e-10;
    private static MCView World()
    {
        return (ViewManager.GetAllViews(false)??Array.Empty<MCView>()).FirstOrDefault(v=>v.Retrieve()&&Close(V(v.ViewOrigin),new())&&
            Close(V(v.ViewMatrix.Row1),new(1,0,0))&&Close(V(v.ViewMatrix.Row2),new(0,1,0))&&Close(V(v.ViewMatrix.Row3),new(0,0,1)))
            ??throw new FixtureException("No existing identity world view is available.");
    }
    public int CopyPlace(int sourceId,Vec3 reference,Vec3 placedReference,double worldZDegrees)
    {
        AssertHostThread();if(!TransactionActive)throw new FixtureException("Native copy requires the owned active transaction.");
        var existing=ReadDocument().Select(e=>e.Id).ToHashSet();
        var world=World();var source=Get(sourceId);var copy=source is SolidGeometry?SolidCopyAdapter.CopyIndependent(sourceId):source.CopyAndTranslate(P(reference),P(placedReference),world,world);
        if(source is SolidGeometry && (placedReference-reference)!=new Vec3(0,0,0)){if(!copy.Translate(P(reference),P(placedReference),world,world)||!copy.Commit())throw new FixtureException("Owned solid translation failed");}
        if(copy==null)throw new FixtureException("Native copy returned null.");
        int copyId=copy.GetEntityID();if(copyId<=0||existing.Contains(copyId))throw new FixtureException("Native copy returned a pre-existing/invalid ID; no transform was applied to it.");
        // Do not reuse the receiver: CopyAndTranslate may rebind its ID. Only the returned owned ID is transformed.
        copy=Get(copyId);
        if(worldZDegrees!=0)
        {
            if(!copy.Rotate(P(placedReference),worldZDegrees,world))throw new FixtureException("Native owned-copy rotation failed.");
            if(copy.GetEntityID()!=copyId)throw new FixtureException("Rotation unexpectedly rebound the owned copy ID.");
            if(!copy.Commit())throw new FixtureException("Native owned-copy rotation commit failed.");
        }
        copy=Get(copyId);
        if(copy.Selected||copy.Blanked)
        {copy.Selected=false;copy.Blanked=false;if(!copy.Commit())throw new FixtureException("Unable to normalize owned-copy display flags.");}
        return copyId;
    }
    public void RestoreFlags(NativeEntityState[] original)
    {
        AssertHostThread();foreach(var row in original)if(Get(row.Id).Blanked!=row.Blanked)throw new FixtureException("Unexpected blanked change");
        var ids=original.Select(r=>r.Id).ToHashSet();var wanted=PorscheAdvanced2027.GeometrySelection.Selected().Where(id=>!ids.Contains(id)).Concat(original.Where(r=>r.Selected).Select(r=>r.Id)).ToArray();
        PorscheAdvanced2027.GeometrySelection.Set(wanted);
    }
    public NativeBounds Measure(int[] ids)
    {
        AssertHostThread();foreach(int id in ids)ValidateSource(id);
        using var selection=new PorscheAdvanced2027.GeometrySelection();PorscheAdvanced2027.GeometrySelection.Set(ids);
        var b=MastercamPluginAI.GeometryAdapter.HostGeometry.MeasureSelected(ids);
        return new(new(b.Min.X,b.Min.Y,b.Min.Z),new(b.Max.X,b.Max.Y,b.Max.Z));
    }

}

internal sealed class NativeViewState
{
    private readonly MCView wcs=ViewManager.WorkCoordinateSystem,cp=ViewManager.CPlane,tp=ViewManager.TPlane,gp=ViewManager.GraphicsView;
    private readonly bool cf=ViewManager.CplaneFollowsWcs,gf=ViewManager.GplaneFollowsWcs,cg=ViewManager.CplaneFollowsGplane,ci=ViewManager.CplaneTopWhenGplaneIso,c3=SettingsManager.ConstructionView3D;
    private readonly double depth=ViewManager.ConstructionDepth;
    private static void Detach(){ViewManager.CplaneFollowsWcs=false;ViewManager.GplaneFollowsWcs=false;ViewManager.CplaneFollowsGplane=false;ViewManager.CplaneTopWhenGplaneIso=false;}
    internal static void Use(MCView frame){Detach();ViewManager.WorkCoordinateSystem=frame;ViewManager.GraphicsView=frame;ViewManager.CPlane=frame;ViewManager.TPlane=frame;SettingsManager.ConstructionView3D=true;}
    internal void Restore()
    {
        Detach();ViewManager.WorkCoordinateSystem=wcs;ViewManager.GraphicsView=gp;ViewManager.CPlane=cp;ViewManager.TPlane=tp;ViewManager.ConstructionDepth=depth;SettingsManager.ConstructionView3D=c3;
        ViewManager.CplaneTopWhenGplaneIso=ci;ViewManager.CplaneFollowsGplane=cg;ViewManager.GplaneFollowsWcs=gf;ViewManager.CplaneFollowsWcs=cf;Verify();
    }
    internal void Verify()
    {
        if(ViewManager.WorkCoordinateSystem.ViewID!=wcs.ViewID||ViewManager.CPlane.ViewID!=cp.ViewID||ViewManager.TPlane.ViewID!=tp.ViewID||ViewManager.GraphicsView.ViewID!=gp.ViewID||
            ViewManager.ConstructionDepth!=depth||SettingsManager.ConstructionView3D!=c3||ViewManager.CplaneTopWhenGplaneIso!=ci||ViewManager.CplaneFollowsGplane!=cg||ViewManager.GplaneFollowsWcs!=gf||ViewManager.CplaneFollowsWcs!=cf)
            throw new FixtureException("Native measurement view/context restoration did not verify.");
    }
}
