#r "__SYSTEM_TEXT_JSON__"
// Bounded synthetic contour trial. Render placeholders with contour_smoke.py.
// No FileManager.New/Open, postprocessing, production files or regeneration on reopen.
new AicncContourSmoke().Run();

public sealed class AicncContourSmoke
{
    private readonly string requestPath = __REQUEST_PATH__;
    private readonly string receiptPath = __RECEIPT_PATH__;
    private readonly string mode = __MODE__;
    private readonly string expectedRequestHash = __REQUEST_SHA256__;
    private readonly AicncPortableJson json =
        new AicncPortableJson();
    private System.Collections.Generic.Dictionary<string, object> request;
    private string stage = "preflight";

    public void Run()
    {
        if (System.IO.File.Exists(receiptPath)) throw new System.Exception("Receipt already exists; do not replay.");
        var result = Obj("schema_version", "aicnc.mastercam-contour-smoke-receipt/0.1",
            "mode", mode, "ok", false, "pid", System.Diagnostics.Process.GetCurrentProcess().Id,
            "utc", System.DateTime.UtcNow.ToString("O"), "production_released", false,
            "regeneration_performed", false);
        try
        {
            Require(Hash(requestPath) == expectedRequestHash, "Request changed after preparation");
            request = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(
                System.IO.File.ReadAllText(requestPath));
            result["request_sha256"] = Hash(requestPath);
            result["run_id"] = S("run_id");
            result["api_version"] = typeof(Mastercam.IO.FileManager).Assembly.FullName;
            result["api_sha256"] = Hash(typeof(Mastercam.IO.FileManager).Assembly.Location);
            result["host_version"] = Mastercam.IO.FileManager.MastercamExeProductVersionName();
            Require(S("schema_version") == "aicnc.mastercam-contour-smoke-request/0.1", "Request version");
            Require(S("purpose") == "synthetic_native_validation", "Synthetic scope required");
            Require(mode == "create" || mode == "reopen", "Unsupported mode");
            Require(Mastercam.IO.SettingsManager.Metric, "Expected metric document");
            string model = System.IO.Path.GetFullPath(S("model_path"));
            Require(System.IO.Path.GetDirectoryName(model) == System.IO.Path.GetDirectoryName(requestPath), "Model must stay in the trial directory");
            Require(System.IO.Path.GetExtension(model).ToLowerInvariant() == ".mcam", "Expected MCAM output");
            if (mode == "create")
            {
                Require(!System.IO.File.Exists(model), "Output already exists");
                Require(!System.IO.File.Exists(Mastercam.IO.FileManager.CurrentFileName), "Refuse an existing document");
                Require(Mastercam.Support.SearchManager.GetGeometry().Length == 0, "Expected empty geometry");
                Require(Mastercam.Support.SearchManager.GetOperations().Length == 0, "Expected no operations");
                Require(D("width_mm") > 0 && D("height_mm") > 0 && D("depth_mm") < 0, "Invalid dimensions");
                Require(D("tool_diameter_mm") > 0 && D("feed_mm_min") > 0 && I("spindle_rpm") > 0, "Invalid tool or cutting data");
                Step("machine_group");
                var groups = new System.Collections.Generic.List<Mastercam.Support.Group>();
                Mastercam.Support.GroupManager.GetAllGroups(groups, true);
                Require(groups.Count == 0, "Expected no machine groups");
                Require(Mastercam.Support.MachineDefManager.CreateMillMachineGroup(), "CreateMillMachineGroup failed");
                Step("geometry");
                var lines = Mastercam.GeometryUtility.GeometryCreationManager.CreateRectangle(
                    new Mastercam.Math.Point3D(0, 0, 0), new Mastercam.Math.Point3D(D("width_mm"), D("height_mm"), 0));
                var geometries = new Mastercam.Database.Geometry[lines.Length];
                for (int i = 0; i < lines.Length; i++) geometries[i] = lines[i];
                var chains = Mastercam.Database.ChainManager.ChainGeometry(geometries);
                Require(chains.Length == 1 && chains[0].IsClosed && chains[0].CurvesCount == 4, "Expected one closed four-line chain");
                chains[0].Direction = Mastercam.Database.Types.ChainDirectionType.CounterClockwise;
                Step("tool");
                var tool = new Mastercam.Tools.EndMillFlatTool {
                    IsMetric = true, Diameter = D("tool_diameter_mm"), Number = 1,
                    DiameterOffset = 1, LengthOffset = 1, Length = 50, FluteLength = 20,
                    ShoulderLength = 25, Flutes = 4, HolderDia = 20, HolderLength = 40,
                    RPM = I("spindle_rpm"), Feed = D("feed_mm_min"), PlungeFeed = 100, RetractFeed = 500,
                    FileName = "", Name = "AICNC synthetic contour validation tool"
                };
                Require(tool.Commit(), "Tool commit failed");
                Step("operation");
                var op = new Mastercam.Operations.ContourOperation();
                op.Name = S("operation_name");
                op.OperationTool = tool;
                op.FeedRate = D("feed_mm_min"); op.SpindleSpeed = I("spindle_rpm");
                op.PlungeRate = 100; op.RetractRate = 500;
                op.LengthOffset = 1; op.DiameterOffset = 1;
                op.CutParams.ContourSubtype = Mastercam.Operations.Types.ContourSubtypeType.Basic;
                op.CutterComp.Type = Mastercam.Database.Types.CutterCompType.CutterCompComputer;
                op.CutterComp.Direction = Mastercam.Database.Types.CutterCompDir.CutterCompRight;
                op.CutterComp.RollCorners = Mastercam.Database.Types.CutterCompRoll.CutterCompRollNone;
                op.LeadInOut.Enabled = false;
                op.Linking.Clearance = 10; op.Linking.ClearanceOn = true;
                op.Linking.ClearanceIncremental = false; op.Linking.ClearanceAssociative = false;
                op.Linking.Retract = 5; op.Linking.RetractOn = true;
                op.Linking.RetractIncremental = false; op.Linking.RetractAssociative = false;
                op.Linking.FeedPlane = 2; op.Linking.FeedPlaneIncremental = false; op.Linking.FeedPlaneAssociative = false;
                op.Linking.TopStock = 0; op.Linking.TopStockIncremental = false; op.Linking.TopStockAssociative = false;
                op.Linking.Depth = D("depth_mm"); op.Linking.DepthIncremental = false; op.Linking.DepthAssociative = false;
                op.SetChainArray(chains);
                Require(op.Commit(), "Operation commit failed");
                Step("regenerate");
                Require(op.Regenerate(), "Regenerate returned false");
                result["regeneration_performed"] = true;
                Step("readback_before_save");
                result["snapshot"] = Readback();
                Step("save");
                Mastercam.Operations.OperationsManager.RefreshOperationsManager();
                Mastercam.IO.GraphicsManager.FitScreen();
                Require(Mastercam.IO.FileManager.SaveAs(model, false), "SaveAs failed");
                Mastercam.IO.FileManager.CurrentFileName = model;
                Require(Mastercam.IO.FileManager.Save(), "Save failed");
            }
            else
            {
                Require(System.String.Equals(System.IO.Path.GetFullPath(Mastercam.IO.FileManager.CurrentFileName),
                    model, System.StringComparison.OrdinalIgnoreCase), "Reopened document mismatch");
                Step("readback_after_reopen");
                result["snapshot"] = Readback();
            }
            Require(System.IO.File.Exists(model), "Native file missing");
            result["model_path"] = model;
            result["machine_sha256"] = Hash(Mastercam.Support.GroupManager.GetMachineNameInActiveGroup());
            result["model_sha256"] = Hash(model);
            result["model_size_bytes"] = new System.IO.FileInfo(model).Length;
            result["current_file"] = Mastercam.IO.FileManager.CurrentFileName;
            result["ok"] = true;
            Step("complete");
        }
        catch (System.Exception ex) { result["error"] = ex.ToString(); }
        result["stage"] = stage;
        using (var stream = new System.IO.FileStream(receiptPath, System.IO.FileMode.CreateNew))
        using (var writer = new System.IO.StreamWriter(stream, new System.Text.UTF8Encoding(false)))
            writer.Write(json.Serialize(result));
    }

    private object Readback()
    {
        var operations = Mastercam.Support.SearchManager.GetOperations();
        Require(operations.Length == 1, "Expected exactly one operation");
        var op = operations[0] as Mastercam.Operations.ContourOperation;
        Require(op != null && op.Name == S("operation_name") && !op.Dirty, "Operation missing, wrong type/name or dirty");
        var tool = op.OperationTool;
        Require(tool != null && tool.IsMetric, "Operation tool missing or nonmetric");
        var chains = op.GetChainArray();
        Require(chains != null && chains.Length == 1 && chains[0].IsClosed && chains[0].CurvesCount == 4, "Chain binding lost");
        var curves = Mastercam.Database.ChainManager.GetGeometryInChain(chains[0]);
        var geometry = new System.Collections.Generic.List<object>();
        foreach (var curve in curves) geometry.Add(Obj("type", curve.GetType().FullName,
            "start", Point(curve.EndPoint1), "end", Point(curve.EndPoint2)));
        var ext = Mastercam.Operations.OperationsManager.GetOperationExtents(op.GetOperationID());
        double zMax, zMin;
        bool zValid = op.GetMaxAndMinZ(out zMax, out zMin);
        double seconds = op.CalcCycleTime();
        Require(ext != null && ext.IsDataValid && ext.IsTravelValid && zValid && seconds > 0 &&
            !double.IsNaN(seconds) && !double.IsInfinity(seconds), "No valid nonempty native toolpath evidence");
        return Obj("metric", Mastercam.IO.SettingsManager.Metric,
            "geometry_count", Mastercam.Support.SearchManager.GetGeometry().Length,
            "operation_count", operations.Length, "operation_id", op.GetOperationID(),
            "operation_type", op.GetType().FullName, "operation_name", op.Name, "dirty", op.Dirty,
            "machine_name", Mastercam.Support.GroupManager.GetMachineNameInActiveGroup(),
            "feed_mm_min", op.FeedRate, "spindle_rpm", op.SpindleSpeed,
            "plunge_mm_min", op.PlungeRate, "retract_mm_min", op.RetractRate,
            "depth_mm", op.Linking.Depth, "top_stock_mm", op.Linking.TopStock,
            "clearance_mm", op.Linking.Clearance, "retract_mm", op.Linking.Retract,
            "feed_plane_mm", op.Linking.FeedPlane, "depth_incremental", op.Linking.DepthIncremental,
            "comp_type", op.CutterComp.Type.ToString(), "comp_direction", op.CutterComp.Direction.ToString(),
            "lead_enabled", op.LeadInOut.Enabled,
            "tool", Obj("type", tool.GetType().FullName, "metric", tool.IsMetric, "number", tool.Number,
                "diameter_mm", tool.Diameter, "length_mm", tool.Length, "flute_length_mm", tool.FluteLength,
                "holder_diameter_mm", tool.HolderDia, "holder_length_mm", tool.HolderLength,
                "length_offset", op.LengthOffset, "diameter_offset", op.DiameterOffset),
            "chain", Obj("count", chains.Length, "curves_count", chains[0].CurvesCount,
                "closed", chains[0].IsClosed, "flat", chains[0].IsFlat, "direction", chains[0].Direction.ToString(),
                "area_mm2", chains[0].Area, "perimeter_mm", chains[0].Perimeter, "curves", geometry),
            "path", Obj("data_valid", ext.IsDataValid, "travel_valid", ext.IsTravelValid,
                "world_min", Point(ext.WorldMin), "world_max", Point(ext.WorldMax),
                "wcs_id", ext.CommonWcsID, "tool_plane_id", ext.CommonTPlaneID,
                "z_min_mm", zMin, "z_max_mm", zMax, "cycle_time_seconds", seconds));
    }

    private void Step(string value) { stage = value; System.IO.File.WriteAllText(receiptPath + ".progress", value); }
    private string S(string key) { return (string)request[key]; }
    private double D(string key) { return System.Convert.ToDouble(request[key], System.Globalization.CultureInfo.InvariantCulture); }
    private int I(string key) { return System.Convert.ToInt32(request[key], System.Globalization.CultureInfo.InvariantCulture); }
    private static void Require(bool condition, string message) { if (!condition) throw new System.Exception(message); }
    private static object Point(Mastercam.Math.Point3D p) { return new double[] {p.x, p.y, p.z}; }
    private static string Hash(string path) {
        using (var sha = System.Security.Cryptography.SHA256.Create())
        using (var stream = System.IO.File.OpenRead(path))
            return System.BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    private static System.Collections.Generic.Dictionary<string, object> Obj(params object[] pairs) {
        var result = new System.Collections.Generic.Dictionary<string, object>();
        for (int i = 0; i < pairs.Length; i += 2) result[(string)pairs[i]] = pairs[i + 1];
        return result;
    }
}

// Compatibility adapter for the original P08 smoke fixture on NET-Script 2027.
public sealed class AicncPortableJson {
 public T Deserialize<T>(string text) {
  using(var doc=System.Text.Json.JsonDocument.Parse(text))return (T)Convert(doc.RootElement);
 }
 public string Serialize(object value) { return System.Text.Json.JsonSerializer.Serialize(value); }
 private static object Convert(System.Text.Json.JsonElement e) {
  switch(e.ValueKind) {
   case System.Text.Json.JsonValueKind.Object:
    var d=new System.Collections.Generic.Dictionary<string,object>();
    foreach(var p in e.EnumerateObject())d[p.Name]=Convert(p.Value);return d;
   case System.Text.Json.JsonValueKind.Array:
    var a=new System.Collections.Generic.List<object>();foreach(var v in e.EnumerateArray())a.Add(Convert(v));return a.ToArray();
   case System.Text.Json.JsonValueKind.String:return e.GetString();
   case System.Text.Json.JsonValueKind.Number:return e.GetDouble();
   case System.Text.Json.JsonValueKind.True:return true;
   case System.Text.Json.JsonValueKind.False:return false;
   default:return null;
  }
 }
}
