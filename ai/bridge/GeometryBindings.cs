using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Mastercam.Database;
using Mastercam.IO;
using PorscheAdvanced2027;
using Edge=MastercamPluginAI.EdgeAdapter;
using Svg=SVGGeometry2027;
using Sketch=TpSketcher2027;
using Hirth=HirthTools2027;
using Radius=MPDesignRadiusSelect2027;
using Surface=MPDesignSurfaceSelect2027;
using Normal=MPDesignTools2027;
using Screen=ScreenTools2027;
using Electrode=ElectrodeReport2027;

namespace MastercamPluginAI;

// Typed business APIs only. Every temporary selection is restored within the callback.
public static class GeometryBindings
{
    static readonly JsonSerializerOptions Json=new(){IncludeFields=true,WriteIndented=true,Converters={new JsonStringEnumConverter()},UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    static string Write(object x)=>JsonSerializer.Serialize(x,Json);
    static T Read<T>(JsonElement x)=>JsonSerializer.Deserialize<T>(x.GetRawText(),Json);
    static int I(JsonElement x,string k)=>x.GetProperty(k).GetInt32();
    static double N(JsonElement x,string k)=>x.GetProperty(k).GetDouble();
    static bool B(JsonElement x,string k)=>x.GetProperty(k).GetBoolean();
    static string S(JsonElement x,string k)=>x.GetProperty(k).GetString();
    static int[] Ids(JsonElement x,string k)=>x.GetProperty(k).EnumerateArray().Select(v=>v.GetInt32()).ToArray();
    static T Selected<T>(int[] ids,Func<T> f){using var selection=new GeometrySelection();GeometrySelection.Set(ids);return f();}
    static void Visible(int[] ids){foreach(int id in ids){var g=Geometry.RetrieveEntity(id);if(g==null||g.Blanked||!LevelsManager.IsLevelVisible(g.Level))throw new ArgumentException("Visible geometry ID required: "+id);}}
    static object Lines(int[] ids)=>ids.Select(id=>new{id,exists=Geometry.RetrieveEntity(id)!=null,shape=Geometry.RetrieveEntity(id)==null?null:PorscheBindings.Shape(id)}).ToArray();
    static FixtureTools2027.Core.Vec3 FV(JsonElement x)=>new(N(x,"x"),N(x,"y"),N(x,"z"));
    static Hirth.Vec3 HV(JsonElement x)=>new(N(x,"x"),N(x,"y"),N(x,"z"));
    static Hirth.AxisGrid Axis(JsonElement x)=>new(S(x,"Label"),HV(x.GetProperty("Direction")),N(x,"MinimumDegrees"),N(x,"MaximumDegrees"),N(x,"StepDegrees"));

    public static PorscheBinding Prepare(JsonElement q,string directory)
    {
        Directory.CreateDirectory(directory);
        string action=S(q,"action");var c=q.GetProperty("parameters");
        var binding=new PorscheBinding();Action apply=null,rollback=null;Func<object> output=null;
        bool preserveDatabase=false;bool restoreExactDatabase=true;
        int[] selectionBefore=GeometrySelection.Selected();
        switch(action) {
        case "mp.edges": {
            int id=I(q,"source_id");Visible(new[]{id});
            var request=new Edge.EdgeRequest(id,Enum.Parse<Edge.EdgeMode>(S(c,"mode")),I(c,"output_level"),N(c,"output_z"),N(c,"tolerance"),I(c,"color"));
            var preview=Selected(new[]{id},()=>Edge.EdgeTools.Preview(request));
            Edge.EdgeReceipt receipt=null;
            binding.Preview=new{action,preview.Request,preview.Geometry,preview.Signature,contract=Edge.EdgeTools.Contract};
            apply=()=>{receipt=Selected(new[]{id},()=>Edge.EdgeTools.Create(request,preview.Signature));if(!receipt.Committed)throw new InvalidOperationException("Edge output did not commit.");};
            rollback=()=>PorscheBindings.DeleteGeometry(receipt.GeometryIds);
            output=()=>new{receipt,geometry=Lines(receipt?.GeometryIds??Array.Empty<int>())};break;
        }
        case "mp.reverse_normals": {
            var ids=Ids(q,"entity_ids");Visible(ids);var host=new Normal.Api29NormalHost();
            var plan=Selected(ids,()=>Normal.Core.NormalWorkflow.Prepare(host));
            if(plan.Surfaces.Count!=ids.Length)throw new ArgumentException("Every ID must be a standalone visible surface.");
            binding.Preview=new{action,surfaces=plan.Surfaces,ignored=plan.IgnoredCount};
            Normal.Core.NormalResult receipt=null;
            apply=()=>receipt=Selected(ids,()=>Normal.Core.NormalWorkflow.Execute(host,plan,true));
            rollback=()=>Selected(ids,()=>{foreach(var s in plan.Surfaces)host.WriteNormal(s.Id,s.Reversed);foreach(var s in plan.Surfaces)if(host.ReadSurface(s.Id)!=s)throw new InvalidOperationException("Normal restoration mismatch.");return true;});
            output=()=>new{receipt,surfaces=Selected(ids,()=>ids.Select(host.ReadSurface).ToArray())};restoreExactDatabase=false;break;
        }
        case "mp.select_surface_types": {
            var types=c.GetProperty("types").EnumerateArray().Select(x=>x.GetString()).ToArray();
            // Candidates() is read-only. Use the verified attribute-only selection adapter on apply.
            using var session=new Surface.Core.SelectionSession(new Surface.Api29Host());
            var candidates=session.Candidates(types);var wanted=selectionBefore.Concat(candidates).Distinct().Order().ToArray();
            binding.Preview=new{action,available=session.Available,types,matched_ids=candidates,selected_before=selectionBefore,selected_after=wanted};
            apply=()=>GeometrySelection.Set(wanted);rollback=()=>GeometrySelection.Set(selectionBefore);
            output=()=>new{selected_ids=GeometrySelection.Selected()};break;
        }
        case "mp.select_radius": {
            var ids=Ids(q,"solid_ids");Visible(ids);var host=new RadiusAdapter.Api29Host();var radiusBefore=host.Capture();
            var request=new Radius.Core.RadiusRequest(ids,c.GetProperty("kinds").EnumerateArray().Select(x=>Enum.Parse<Radius.Core.RadiusKind>(x.GetString())).ToArray(),N(c,"minimum"),N(c,"maximum"));
            request.Validate(radiusBefore);var faces=host.ReadFaces(ids);Radius.Core.Snapshot.Same(radiusBefore,host.Capture());
            var matches=Radius.Core.RadiusFilter.Match(faces,request);var wanted=selectionBefore.Concat(matches.Select(x=>x.BodyId)).Distinct().Order().ToArray();
            binding.Preview=new{action,request,matches,selected_before=selectionBefore,selected_after=wanted};
            apply=()=>{if(!faces.SequenceEqual(host.ReadFaces(ids)))throw new InvalidOperationException("Analytic face data changed.");GeometrySelection.Set(wanted);};
            rollback=()=>GeometrySelection.Set(selectionBefore);output=()=>new{matches,selected_ids=GeometrySelection.Selected()};break;
        }
        case "xplus.svg": {
            var plan=Svg.SvgGeometry.PrepareXml(S(q,"svg_xml"),Read<Svg.SvgImportOptions>(c));Svg.SvgImportResult receipt=null;
            binding.Preview=new{action,plan.Geometry.SourceSha256,plan.Geometry.Options,plan.Geometry.Min,plan.Geometry.Max,plan.Geometry.Notes,segment_count=plan.Geometry.Segments.Count,segments=plan.Geometry.Segments};
            apply=()=>{receipt=Svg.SvgGeometry.Execute(plan);if(!receipt.Success||receipt.RequiresHostReview)throw new InvalidOperationException(receipt.Failure??"SVG readback failed.");};
            rollback=()=>PorscheBindings.DeleteGeometry(receipt.CreatedIds);output=()=>new{receipt,geometry=Lines(receipt?.CreatedIds??Array.Empty<int>())};break;
        }
        case "xplus.sketch": {
            var host=new SketchHostAdapter();var plane=host.Plane(I(q,"plane_id"));
            var chains=c.GetProperty("chains").EnumerateArray().Select(chain=>chain.EnumerateArray().Select(p=>new Sketch.V2(N(p,"x"),N(p,"y"))).ToArray()).ToArray();
            var plan=new Sketch.SketchPlan(plane,N(c,"depth"),N(c,"diameter"),chains);
            var m=c.GetProperty("machining");var settings=new Sketch.CreateSettings(I(c,"level"),I(c,"color"),m.ValueKind==JsonValueKind.Null?null:Read<Sketch.MachiningSettings>(m),null,c.GetProperty("existing_tool_slot").ValueKind==JsonValueKind.Null?null:I(c,"existing_tool_slot"));
            settings.Validate(plan);if(settings.ExistingToolSlot.HasValue)host.ValidateExistingTool(settings.ExistingToolSlot.Value,plan.Diameter);
            if(!LevelsManager.IsLevelVisible(settings.Level))throw new ArgumentException("Existing visible output level required.");
            SketchExecution.Receipt receipt=null;binding.Preview=new{action,plan,settings};
            apply=()=>receipt=SketchExecution.Create(host,plan,settings);rollback=()=>SketchExecution.Rollback(host,receipt);
            output=()=>new{receipt,actual=receipt?.Objects.Select(o=>host.Read(o.Object)).ToArray()};break;
        }
        case "xplus.fixture_copy": {
            var ids=Ids(q,"entity_ids");Visible(ids);
            var reference=FV(c.GetProperty("reference"));var target=FV(c.GetProperty("target"));var translation=FV(c.GetProperty("translation"));double degrees=N(c,"world_z_degrees");
            // Measurement is scoped and restores its temporary corners, planes and selection.
            var bounds=Selected(ids,()=>MastercamPluginAI.GeometryAdapter.HostGeometry.MeasureSelected(ids));
            FixtureTools2027.Core.NativePlacementReport receipt=null;
            binding.Preview=new{action,source_ids=ids,bounds,reference,target,translation,world_z_degrees=degrees,copy_count=ids.Length};
            apply=()=>{receipt=Selected(ids,()=>FixtureAdapter.NativeFixtureCopy.PlaceSelected(reference,target,translation,degrees));if(receipt.Status!="committed"||receipt.RequiresHostReview)throw new InvalidOperationException("Native fixture placement: "+receipt.Status);};
            rollback=()=>PorscheBindings.DeleteGeometry(receipt.CreatedIds);output=()=>new{receipt,geometry=Lines(receipt?.CreatedIds??Array.Empty<int>())};break;
        }
        case "xplus.fit_plane": {
            var settings=new Hirth.FitSettings(Axis(c.GetProperty("tilt")),Axis(c.GetProperty("rotary")),N(c,"tolerance_degrees"),I(c,"maximum_candidates"));
            var plan=Hirth.HostPlanes.PreviewPlane(I(q,"plane_id"),settings);
            var options=new Hirth.CommitOptions(S(c,"name_prefix"),B(c,"reuse_matching"),B(c,"activate")?Hirth.PlaneActivation.ToolAndConstruction:Hirth.PlaneActivation.None);
            Hirth.PlaneCommitResult receipt=null;binding.Preview=new{action,plan,options};
            apply=()=>receipt=Hirth.HostPlanes.Commit(plan,options);rollback=()=>{if(receipt.Change!=null)Hirth.HostPlanes.Rollback(receipt.Change);};
            output=()=>new{receipt,actual=receipt==null?null:Hirth.HostPlanes.ListPlanes().SingleOrDefault(p=>p.Id==receipt.PlaneId)};break;
        }
        case "xplus.setup_sheet": {
            bool all=B(c,"all_operations"),screenshot=B(c,"include_screenshot");
            var ids=Mastercam.Support.SearchManager.GetOperationIDs(all);SetupSheets2027.ExportReceipt receipt=null;
            binding.Preview=new{action,operation_ids=ids,include_screenshot=screenshot,artifact_policy="unique request directory",scope=all?"all":"selected"};
            apply=()=>receipt=SetupSheets2027.ReportService.ExportToDirectory(directory,all,screenshot);
            rollback=()=>{};output=()=>new{receipt,artifacts_retained=true};preserveDatabase=true;break;
        }
        case "xplus.levels_to_stl": {
            double tolerance=N(c,"tolerance");var state=LevelExport2027.ExportService.CaptureState();LevelExport2027.Core.ExportResult receipt=null;
            binding.Preview=new{action,tolerance,state.Levels,state.Entities,artifact_policy="unique request directory"};
            apply=()=>{receipt=LevelExport2027.Core.ExportCoordinator.Run(new AttributeOnlyLevelExport(),directory,tolerance);if(receipt.Status!="PASS"||!receipt.StateRestored||receipt.Errors.Count!=0)throw new InvalidOperationException("Level STL export failed; inspect receipt.");};
            rollback=()=>{};output=()=>new{receipt,artifacts_retained=true};preserveDatabase=true;break;
        }
        case "xplus.capture": {
            Screen.CaptureResult receipt=null;Screen.SavedImage saved=null;
            var options=new Screen.CaptureOptions(B(c,"show_view_axes"),B(c,"show_wcs_axes"));binding.Preview=new{action,options,artifact_policy="unique request directory"};
            apply=()=>{receipt=Screen.ScreenTools.CaptureWhite(options);if(!receipt.State.Success||!receipt.State.StateRestored||receipt.State.RequiresHostReview)throw new InvalidOperationException(receipt.State.Failure??"Screenshot state restoration failed.");saved=receipt.Image.SaveNewPng(Path.Combine(directory,"view.png"));};
            rollback=()=>{};output=()=>new{state=receipt?.State,saved,artifacts_retained=true};preserveDatabase=true;break;
        }
        case "xplus.gradient": {
            var option=Enum.Parse<Mastercam.IO.Types.GradientOption>(S(c,"option"));Screen.GradientResult receipt=null;
            binding.Preview=new{action,option,before=Screen.BackgroundState.Read()};
            apply=()=>{receipt=Screen.ScreenTools.SetGradient(option);if(!receipt.State.Success||receipt.State.RequiresHostReview)throw new InvalidOperationException(receipt.State.Failure??"Background change failed.");};
            rollback=()=>{var r=Screen.ScreenTools.RestoreGradient(receipt.Lease);if(!r.Success||!r.StateRestored)throw new InvalidOperationException(r.Failure??"Background restore failed.");};
            output=()=>new{receipt,current=Screen.BackgroundState.Read()};break;
        }
        case "xplus.electrode_report": {
            var ids=Ids(q,"entity_ids");Visible(ids);int plane=I(q,"plane_id");
            var capture=Selected(ids,()=>Electrode.MastercamReportReader.InspectSelected(plane));
            var references=c.GetProperty("references").EnumerateArray().Select(r=>new Electrode.ReferenceInput(I(r,"entity_id"),S(r,"label"),Enum.Parse<Electrode.ReferenceSource>(S(r,"source")),r.GetProperty("world_coordinate").ValueKind==JsonValueKind.Null?null:new Electrode.V3(N(r.GetProperty("world_coordinate"),"x"),N(r.GetProperty("world_coordinate"),"y"),N(r.GetProperty("world_coordinate"),"z")),r.GetProperty("user_c_degrees").ValueKind==JsonValueKind.Null?null:N(r,"user_c_degrees"))).ToArray();
            var report=Selected(ids,()=>Electrode.MastercamReportReader.CreateReport(capture,references,S(c,"title"),I(c,"precision")));
            string[] files=Array.Empty<string>();binding.Preview=new{action,capture,references,title=S(c,"title"),precision=I(c,"precision"),artifact_policy="unique request directory"};
            apply=()=>files=Electrode.ReportOutput.WriteNewDirectory(report,Path.Combine(directory,"electrodes"));rollback=()=>{};
            output=()=>new{files,report,artifacts_retained=true};preserveDatabase=true;break;
        }
        default: { var extra=UtilityBindings.Prepare(q,directory);binding.Preview=extra.Preview;apply=extra.Apply;rollback=extra.Rollback;output=extra.Readback;if(action=="xplus.rename_nci")restoreExactDatabase=false;break; }
        }
        string before=PorscheBindings.DatabaseStamp(),after=null,status="Prepared";int[] selectedAfter=null;
        string audit=Path.Combine(directory,"geometry-adapter.json");
        File.WriteAllText(Path.Combine(directory,"database-before.json"),Write(PorscheBindings.DatabaseFacts()));
        object Readback()=>new{status,audit_path=audit,output=output()};
        void Save()=>File.WriteAllText(audit,Write(Readback()));
        binding.Apply=()=>{try{apply();after=PorscheBindings.DatabaseStamp();selectedAfter=GeometrySelection.Selected();if(preserveDatabase&&after!=before)throw new InvalidOperationException("Read/export changed database; inspect audit.");status="Applied";Save();}catch{status="Failed";Save();throw;}};
        binding.Rollback=()=>{
            if(status!="Applied"||after!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Database changed after apply; rollback refused.");
            if(action.StartsWith("mp.select_")&&!selectedAfter.SequenceEqual(GeometrySelection.Selected()))throw new InvalidOperationException("Selection changed after apply; rollback refused.");
            rollback();File.WriteAllText(Path.Combine(directory,"database-after-rollback.json"),Write(PorscheBindings.DatabaseFacts()));if(restoreExactDatabase&&before!=PorscheBindings.DatabaseStamp())throw new InvalidOperationException("Rollback differs from database baseline.");status="RolledBack";Save();
        };
        binding.Readback=Readback;return binding;
    }
}
