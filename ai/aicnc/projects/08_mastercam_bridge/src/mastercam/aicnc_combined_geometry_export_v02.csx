// AI-CNC prospective combined read-only geometry export v0.2.
// One isolated Mastercam process emits Solid STL anchors and Curve geometry sidecars.
// The target Curve remains excluded from transform fitting by the downstream gate.

var entityStlExporter = new AicncEntityStlAnchorExporter();
entityStlExporter.Run();
var curveGeometryExporter = new AicncCurveGeometrySidecarExporter();
curveGeometryExporter.Run();

// AI-CNC Mastercam 2026 read-only entity-level STL geometry anchor.
//
// Each existing Solid entity is written to a new ASCII STL in world coordinates
// by explicit entity ID.  The active project must be an isolated read-only copy;
// no selection, database, operation, save, regenerate, post, or source mutation
// call is made.



public sealed class AicncEntityStlAnchorExporter
{
    private const string SchemaVersion = "aicnc.mastercam-entity-stl-anchor/0.1";
    private const string ScriptId = "aicnc-mastercam-entity-stl-anchor-exporter/0.1";
    private const double ToleranceMm = 0.01;

    public void Run()
    {
        var outputDirectory = System.IO.Path.GetFullPath(RequireEnvironment("AICNC_MASTERCAM_EXPORT_DIR"));
        if (!System.IO.Directory.Exists(outputDirectory))
        { throw new System.InvalidOperationException("The export directory does not exist."); }
        var currentFile = Mastercam.IO.FileManager.CurrentFileName;
        if (string.IsNullOrWhiteSpace(currentFile) || !System.IO.File.Exists(currentFile))
        { throw new System.InvalidOperationException("A Mastercam project copy must be open."); }
        currentFile = System.IO.Path.GetFullPath(currentFile);
        if ((System.IO.File.GetAttributes(currentFile) & System.IO.FileAttributes.ReadOnly) == 0)
        { throw new System.InvalidOperationException("The active project is not a read-only copy."); }

        var projectSha256 = HashFile(currentFile);
        if (!string.Equals(projectSha256, RequireSha256Environment("AICNC_MASTERCAM_EXPECTED_SHA256"),
            System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The active project hash does not match the request."); }
        var role = RequireEnvironment("AICNC_MASTERCAM_DISCOVERY_ROLE");
        var catalog = RequireSha256Environment("AICNC_MASTERCAM_CATALOG_MANIFEST_SHA256");
        var assetId = RequireEnvironment("AICNC_MASTERCAM_ASSET_ID");
        var partId = RequireEnvironment("AICNC_MASTERCAM_PART_ID");
        if (role != "a4_non_factory3_semantic_discovery" ||
            !System.Text.RegularExpressions.Regex.IsMatch(assetId, "^asset-[0-9a-f]{16}$") ||
            !System.Text.RegularExpressions.Regex.IsMatch(partId, "^factory-[0-9a-f]{16}$"))
        { throw new System.InvalidOperationException("The A4 authorization is invalid."); }

        var solids = Mastercam.Support.SearchManager.GetSolidGeometry();
        if (solids == null) { solids = new Mastercam.Database.SolidGeometry[0]; }
        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var outputPath = System.IO.Path.Combine(outputDirectory, "msta-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        { throw new System.InvalidOperationException("The append-only entity STL anchor already exists."); }

        var solidOutput = new System.Collections.Generic.List<object>();
        var apiSuccessCount = 0;
        var validStlCount = 0;
        var outputFileCount = 0;
        var totalTriangleCount = 0;
        for (var index = 0; index < solids.Length; index++)
        {
            var solid = solids[index];
            var entityId = solid.GetEntityID();
            var solidId = "solid-" + entityId.ToString("D8", System.Globalization.CultureInfo.InvariantCulture);
            var stlFile = "mcstl-" + suffix + "-" + solidId + ".stl";
            var stlPath = System.IO.Path.Combine(outputDirectory, stlFile);
            if (System.IO.File.Exists(stlPath))
            { throw new System.InvalidOperationException("The append-only entity STL file already exists."); }

            var apiReturned = false;
            string errorHash = null;
            try
            {
                apiReturned = Mastercam.IO.FileManager.WriteSTL(
                    stlPath, entityId, ToleranceMm, true, true, false, true, true);
            }
            catch (System.Exception error)
            { errorHash = HashText(error.GetType().FullName); }
            if (apiReturned) { apiSuccessCount++; }
            var metrics = InspectAsciiStl(stlPath, apiReturned, errorHash);
            if ((bool)metrics["file_exists"]) { outputFileCount++; }
            if ((string)metrics["status"] == "valid_ascii_stl")
            {
                validStlCount++;
                totalTriangleCount += (int)metrics["triangle_count"];
            }
            solidOutput.Add(Object(
                "solid_id", solidId,
                "runtime_class", solid.GetType().FullName,
                "level", solid.Level,
                "name_sha256", HashText(solid.Name ?? ""),
                "stl_file", stlFile,
                "api_returned", apiReturned,
                "status", metrics["status"],
                "error_type_sha256", metrics["error_type_sha256"],
                "file_size_bytes", metrics["file_size_bytes"],
                "stl_sha256", metrics["stl_sha256"],
                "vertex_count", metrics["vertex_count"],
                "triangle_count", metrics["triangle_count"],
                "bounding_box", metrics["bounding_box"]));
        }

        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The read-only project changed during STL export."); }
        var payload = Object(
            "schema_version", SchemaVersion,
            "anchor_id", "msta-" + suffix,
            "project", Object(
                "project_sha256", projectSha256,
                "copy_sha256_after", copySha256After,
                "source_copy_mode", "isolated_read_only_copy",
                "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", role,
                "catalog_manifest_sha256", catalog,
                "asset_id", assetId,
                "part_id", partId,
                "factory3_excluded", true),
            "host", Object(
                "product", "Mastercam",
                "file_version", System.Diagnostics.FileVersionInfo.GetVersionInfo(
                    typeof(Mastercam.IO.FileManager).Assembly.Location).FileVersion,
                "api_assembly_version", typeof(Mastercam.IO.FileManager).Assembly.GetName().Version.ToString(),
                "script_id", ScriptId),
            "policy", Object(
                "source_mutations_permitted", false,
                "database_commit_calls", 0,
                "selection_mutation_calls", 0,
                "write_stl_calls", solids.Length,
                "external_output_file_count", outputFileCount,
                "operation_names_exported", false,
                "customer_fields_exported", false,
                "operation_is_feature_label", false),
            "export_config", Object(
                "specific_entity_id", true,
                "tolerance_mm", ToleranceMm,
                "ascii", true,
                "silent", true,
                "use_wcs", false,
                "ok_if_not_visible", true,
                "ok_if_blanked", true),
            "solids", solidOutput,
            "summary", Object(
                "solid_count", solids.Length,
                "api_success_count", apiSuccessCount,
                "valid_stl_count", validStlCount,
                "invalid_stl_count", solids.Length - validStlCount,
                "total_triangle_count", totalTriangleCount,
                "external_output_file_count", outputFileCount),
            "coordinate_frame", "mastercam_world",
            "detailed_curve_geometry_accessed", false,
            "automatic_face_binding_authorized", false,
            "training_authorized", false,
            "factory_test_defined", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O", System.Globalization.CultureInfo.InvariantCulture));
        var temporaryPath = outputPath + ".tmp-" + System.Guid.NewGuid().ToString("N");
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
    }

    private static System.Collections.Generic.Dictionary<string, object> InspectAsciiStl(
        string path, bool apiReturned, string errorHash)
    {
        if (!System.IO.File.Exists(path) || new System.IO.FileInfo(path).Length == 0)
        {
            return Object(
                "file_exists", false,
                "status", errorHash != null ? "api_error" : apiReturned ? "missing_or_empty_file" : "api_returned_false",
                "error_type_sha256", errorHash,
                "file_size_bytes", null,
                "stl_sha256", null,
                "vertex_count", 0,
                "triangle_count", 0,
                "bounding_box", null);
        }
        var size = new System.IO.FileInfo(path).Length;
        try
        {
            var minimum = new double[] { double.PositiveInfinity, double.PositiveInfinity, double.PositiveInfinity };
            var maximum = new double[] { double.NegativeInfinity, double.NegativeInfinity, double.NegativeInfinity };
            var vertexCount = 0;
            using (var reader = new System.IO.StreamReader(path, System.Text.Encoding.ASCII, true))
            {
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    line = line.Trim();
                    if (!line.StartsWith("vertex ", System.StringComparison.OrdinalIgnoreCase)) { continue; }
                    var fields = line.Split((char[])null, System.StringSplitOptions.RemoveEmptyEntries);
                    if (fields.Length != 4) { throw new System.FormatException("Invalid ASCII STL vertex."); }
                    for (var axis = 0; axis < 3; axis++)
                    {
                        var value = double.Parse(fields[axis + 1], System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture);
                        if (double.IsNaN(value) || double.IsInfinity(value))
                        { throw new System.FormatException("Non-finite ASCII STL vertex."); }
                        if (value < minimum[axis]) { minimum[axis] = value; }
                        if (value > maximum[axis]) { maximum[axis] = value; }
                    }
                    vertexCount++;
                }
            }
            if (vertexCount == 0 || vertexCount % 3 != 0)
            { throw new System.FormatException("ASCII STL vertex count is not a positive multiple of three."); }
            var span = new double[] {
                maximum[0] - minimum[0], maximum[1] - minimum[1], maximum[2] - minimum[2] };
            return Object(
                "file_exists", true,
                "status", "valid_ascii_stl",
                "error_type_sha256", null,
                "file_size_bytes", size,
                "stl_sha256", HashFile(path),
                "vertex_count", vertexCount,
                "triangle_count", vertexCount / 3,
                "bounding_box", Object(
                    "minimum", new object[] { minimum[0], minimum[1], minimum[2] },
                    "maximum", new object[] { maximum[0], maximum[1], maximum[2] },
                    "span", new object[] { span[0], span[1], span[2] }));
        }
        catch (System.Exception error)
        {
            return Object(
                "file_exists", true,
                "status", "invalid_ascii_stl",
                "error_type_sha256", HashText(error.GetType().FullName),
                "file_size_bytes", size,
                "stl_sha256", HashFile(path),
                "vertex_count", 0,
                "triangle_count", 0,
                "bounding_box", null);
        }
    }

    private static string RequireEnvironment(string name)
    {
        var value = System.Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value))
        { throw new System.InvalidOperationException(name + " is required."); }
        return value.Trim();
    }

    private static string RequireSha256Environment(string name)
    {
        var value = RequireEnvironment(name).ToUpperInvariant();
        if (!System.Text.RegularExpressions.Regex.IsMatch(value, "^[0-9A-F]{64}$"))
        { throw new System.InvalidOperationException(name + " must be an uppercase SHA-256 digest."); }
        return value;
    }

    private static string HashFile(string path)
    {
        using (var algorithm = System.Security.Cryptography.SHA256.Create())
        using (var stream = new System.IO.FileStream(path, System.IO.FileMode.Open,
            System.IO.FileAccess.Read, System.IO.FileShare.ReadWrite))
        { return Hex(algorithm.ComputeHash(stream)); }
    }

    private static string HashText(string value)
    {
        using (var algorithm = System.Security.Cryptography.SHA256.Create())
        { return Hex(algorithm.ComputeHash(System.Text.Encoding.UTF8.GetBytes(value ?? ""))); }
    }

    private static string Hex(byte[] bytes)
    {
        var builder = new System.Text.StringBuilder(bytes.Length * 2);
        foreach (var item in bytes) { builder.Append(item.ToString("X2")); }
        return builder.ToString();
    }

    private static System.Collections.Generic.Dictionary<string, object> Object(params object[] values)
    {
        var output = new System.Collections.Generic.Dictionary<string, object>();
        for (var index = 0; index < values.Length; index += 2)
        { output.Add((string)values[index], values[index + 1]); }
        return output;
    }

    private static string Json(object value)
    {
        if (value == null) { return "null"; }
        var text = value as string;
        if (text != null) { return "\"" + EscapeJson(text) + "\""; }
        if (value is bool) { return (bool)value ? "true" : "false"; }
        if (value is System.Enum) { return "\"" + EscapeJson(value.ToString()) + "\""; }
        if (value is byte || value is sbyte || value is short || value is ushort ||
            value is int || value is uint || value is long || value is ulong ||
            value is float || value is double || value is decimal)
        { return System.Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture); }
        var dictionary = value as System.Collections.IDictionary;
        if (dictionary != null)
        {
            var fields = new System.Collections.Generic.List<string>();
            foreach (System.Collections.DictionaryEntry entry in dictionary)
            { fields.Add("\"" + EscapeJson((string)entry.Key) + "\":" + Json(entry.Value)); }
            return "{" + string.Join(",", fields.ToArray()) + "}";
        }
        var enumerable = value as System.Collections.IEnumerable;
        if (enumerable != null)
        {
            var items = new System.Collections.Generic.List<string>();
            foreach (var item in enumerable) { items.Add(Json(item)); }
            return "[" + string.Join(",", items.ToArray()) + "]";
        }
        throw new System.InvalidOperationException("Unsupported JSON type: " + value.GetType().FullName);
    }

    private static string EscapeJson(string value)
    {
        var builder = new System.Text.StringBuilder();
        foreach (var character in value)
        {
            switch (character)
            {
                case '\\': builder.Append("\\\\"); break;
                case '"': builder.Append("\\\""); break;
                case '\b': builder.Append("\\b"); break;
                case '\f': builder.Append("\\f"); break;
                case '\n': builder.Append("\\n"); break;
                case '\r': builder.Append("\\r"); break;
                case '\t': builder.Append("\\t"); break;
                default:
                    if (character < 32) { builder.Append("\\u" + ((int)character).ToString("X4")); }
                    else { builder.Append(character); }
                    break;
            }
        }
        return builder.ToString();
    }
}


// AI-CNC Mastercam 2026 read-only Curve geometry sidecar exporter.
//
// This script supplements, but never rewrites, the frozen 0.2 mapping export.
// It runs only on an isolated file-system read-only project copy and emits no
// names or source paths. It does not create labels or mutate Mastercam data.



public sealed class AicncCurveGeometrySidecarExporter
{
    private const string SchemaVersion = "aicnc.mastercam-curve-geometry/0.1";
    private const string ScriptId = "aicnc-mastercam-curve-geometry-exporter/0.1";

    public void Run()
    {
        var outputDirectory = RequireEnvironment("AICNC_MASTERCAM_EXPORT_DIR");
        outputDirectory = System.IO.Path.GetFullPath(outputDirectory);
        if (!System.IO.Directory.Exists(outputDirectory))
        {
            throw new System.InvalidOperationException("The export directory does not exist.");
        }
        var currentFile = Mastercam.IO.FileManager.CurrentFileName;
        if (string.IsNullOrWhiteSpace(currentFile) || !System.IO.File.Exists(currentFile))
        {
            throw new System.InvalidOperationException("A Mastercam project copy must be open.");
        }
        currentFile = System.IO.Path.GetFullPath(currentFile);
        if ((System.IO.File.GetAttributes(currentFile) & System.IO.FileAttributes.ReadOnly) == 0)
        {
            throw new System.InvalidOperationException("The active project is not a read-only copy.");
        }
        var projectSha256 = HashFile(currentFile);
        var expected = RequireSha256Environment("AICNC_MASTERCAM_EXPECTED_SHA256");
        if (!string.Equals(projectSha256, expected, System.StringComparison.Ordinal))
        {
            throw new System.InvalidOperationException("The active project hash does not match the request.");
        }
        var role = RequireEnvironment("AICNC_MASTERCAM_DISCOVERY_ROLE");
        var catalog = RequireSha256Environment("AICNC_MASTERCAM_CATALOG_MANIFEST_SHA256");
        var assetId = RequireEnvironment("AICNC_MASTERCAM_ASSET_ID");
        var partId = RequireEnvironment("AICNC_MASTERCAM_PART_ID");
        if (role != "a4_non_factory3_semantic_discovery" ||
            !System.Text.RegularExpressions.Regex.IsMatch(assetId, "^asset-[0-9a-f]{16}$") ||
            !System.Text.RegularExpressions.Regex.IsMatch(partId, "^factory-[0-9a-f]{16}$"))
        {
            throw new System.InvalidOperationException("The A4 authorization is invalid.");
        }

        var sourceCurveCount = 0;
        var exportedCurveCount = 0;
        var extractionFailureCount = 0;
        var kindCounts = new System.Collections.Generic.Dictionary<string, int>();
        var operationsOutput = new System.Collections.Generic.List<object>();
        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations != null)
        {
            for (var operationIndex = 0; operationIndex < operations.Length; operationIndex++)
            {
                var operation = operations[operationIndex];
                var chainOperation = operation as Mastercam.Operations.ChainBasedOperation;
                if (chainOperation == null)
                {
                    continue;
                }
                var sourceOperationId = operation.GetOperationID();
                var chainsOutput = new System.Collections.Generic.List<object>();
                var operationChains = chainOperation.GetChainArray();
                if (operationChains != null)
                {
                    for (var chainIndex = 0; chainIndex < operationChains.Length; chainIndex++)
                    {
                        var curvesOutput = new System.Collections.Generic.List<object>();
                        var chain = operationChains[chainIndex];
                        Mastercam.Database.CurveGeometry[] geometry = null;
                        try
                        {
                            geometry = Mastercam.Database.ChainManager.GetGeometryInChain(chain);
                        }
                        catch
                        {
                            geometry = null;
                        }
                        var count = geometry == null ? 0 : geometry.Length;
                        sourceCurveCount += count;
                        for (var curveIndex = 0; curveIndex < count; curveIndex++)
                        {
                            var curve = geometry[curveIndex];
                            if (curve == null)
                            {
                                extractionFailureCount++;
                                continue;
                            }
                            try
                            {
                                var curveId = "curve-" + sourceOperationId.ToString("D6") + "-" +
                                    chainIndex.ToString("D4") + "-" + curveIndex.ToString("D4");
                                var record = ExportCurve(curveId, curve);
                                curvesOutput.Add(record);
                                exportedCurveCount++;
                                var kind = (string)record["kind"];
                                if (!kindCounts.ContainsKey(kind)) { kindCounts[kind] = 0; }
                                kindCounts[kind]++;
                            }
                            catch
                            {
                                extractionFailureCount++;
                            }
                        }
                        chainsOutput.Add(Object(
                            "chain_id", "chain-" + sourceOperationId.ToString("D6") + "-" + chainIndex.ToString("D4"),
                            "source_curve_count", count,
                            "exported_curve_count", curvesOutput.Count,
                            "curves", curvesOutput));
                    }
                }
                operationsOutput.Add(Object(
                    "operation_id", "op-" + sourceOperationId.ToString("D6"),
                    "chains", chainsOutput));
            }
        }
        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        {
            throw new System.InvalidOperationException("The read-only project changed during export.");
        }
        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var payload = Object(
            "schema_version", SchemaVersion,
            "curve_export_id", "mcg-" + suffix,
            "project", Object(
                "project_sha256", projectSha256,
                "copy_sha256_after", copySha256After,
                "source_copy_mode", "isolated_read_only_copy",
                "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", role,
                "catalog_manifest_sha256", catalog,
                "asset_id", assetId,
                "part_id", partId,
                "factory3_excluded", true),
            "host", Object(
                "product", "Mastercam",
                "file_version", System.Diagnostics.FileVersionInfo.GetVersionInfo(
                    typeof(Mastercam.IO.FileManager).Assembly.Location).FileVersion,
                "api_assembly_version", typeof(Mastercam.IO.FileManager).Assembly.GetName().Version.ToString(),
                "script_id", ScriptId),
            "policy", Object(
                "source_mutations_permitted", false,
                "mutation_calls_made", false,
                "operation_names_exported", false,
                "customer_fields_exported", false,
                "operation_is_feature_label", false),
            "operations", operationsOutput,
            "summary", Object(
                "source_curve_count", sourceCurveCount,
                "exported_curve_count", exportedCurveCount,
                "curve_extraction_failure_count", extractionFailureCount,
                "curve_kind_counts", kindCounts),
            "training_authorized", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O"));
        var outputPath = System.IO.Path.Combine(outputDirectory, "mcg-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        {
            throw new System.InvalidOperationException("The append-only Curve sidecar already exists.");
        }
        var temporaryPath = outputPath + ".tmp";
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
    }

    private static System.Collections.Generic.Dictionary<string, object> ExportCurve(
        string curveId, Mastercam.Database.CurveGeometry curve)
    {
        var start = PointArray(curve.EndPoint1);
        var end = PointArray(curve.EndPoint2);
        var line = curve as Mastercam.Curves.LineGeometry;
        if (line != null)
        {
            return Object("curve_id", curveId, "runtime_class", curve.GetType().FullName,
                "kind", "line", "start", start, "end", end,
                "line", Object("length", Distance(curve.EndPoint1, curve.EndPoint2)),
                "arc", null, "nurbs", null, "coordinate_frame", "mastercam_model");
        }
        var arc = curve as Mastercam.Curves.ArcGeometry;
        if (arc != null)
        {
            var data = arc.Data;
            return Object("curve_id", curveId, "runtime_class", curve.GetType().FullName,
                "kind", "arc", "start", start, "end", end, "line", null,
                "arc", Object(
                    "center", PointArray(data.CenterPoint),
                    "radius", SafeDouble(data.Radius),
                    "start_angle_deg", SafeDouble(data.StartAngleDegrees),
                    "end_angle_deg", SafeDouble(data.EndAngleDegrees),
                    "view", ExportView(arc.View)),
                "nurbs", null, "coordinate_frame", "mastercam_model");
        }
        var nurbs = curve as Mastercam.Curves.NURBSCurveGeometry;
        if (nurbs != null)
        {
            return Object("curve_id", curveId, "runtime_class", curve.GetType().FullName,
                "kind", "nurbs", "start", start, "end", end, "line", null, "arc", null,
                "nurbs", Object(
                    "degree", (int)nurbs.Degree,
                    "dimension", (int)nurbs.Dimension,
                    "is_closed", nurbs.IsClosed,
                    "is_periodic", nurbs.IsPeriodic,
                    "is_planar", nurbs.IsPlanar,
                    "is_uniform", nurbs.IsUniform,
                    "is_non_rational", nurbs.IsNonRational,
                    "length", SafeDouble(nurbs.Length),
                    "normal", PointArray(nurbs.Normal),
                    "control_points", PointArrays(nurbs.ControlPoints),
                    "knots", NumberArray(nurbs.Knots)),
                "coordinate_frame", "mastercam_model");
        }
        return Object("curve_id", curveId, "runtime_class", curve.GetType().FullName,
            "kind", "unsupported", "start", start, "end", end,
            "line", null, "arc", null, "nurbs", null,
            "coordinate_frame", "mastercam_model");
    }

    private static object ExportView(Mastercam.Database.MCView view)
    {
        if (view == null) { return null; }
        var origin = view.ViewOrigin;
        var matrix = view.ViewMatrix;
        return Object(
            "origin", PointArray(origin),
            "matrix", new object[] {
                new object[] { SafeDouble(matrix.Row1.x), SafeDouble(matrix.Row1.y), SafeDouble(matrix.Row1.z) },
                new object[] { SafeDouble(matrix.Row2.x), SafeDouble(matrix.Row2.y), SafeDouble(matrix.Row2.z) },
                new object[] { SafeDouble(matrix.Row3.x), SafeDouble(matrix.Row3.y), SafeDouble(matrix.Row3.z) }
            });
    }

    private static object[] PointArray(Mastercam.Math.Point3D point)
    { return new object[] { SafeDouble(point.x), SafeDouble(point.y), SafeDouble(point.z) }; }

    private static object[] PointArrays(Mastercam.Math.Point3D[] points)
    {
        if (points == null) { return new object[0]; }
        var output = new object[points.Length];
        for (var index = 0; index < points.Length; index++) { output[index] = PointArray(points[index]); }
        return output;
    }

    private static object[] NumberArray(double[] values)
    {
        if (values == null) { return new object[0]; }
        var output = new object[values.Length];
        for (var index = 0; index < values.Length; index++) { output[index] = SafeDouble(values[index]); }
        return output;
    }

    private static double Distance(Mastercam.Math.Point3D left, Mastercam.Math.Point3D right)
    {
        var x = left.x - right.x; var y = left.y - right.y; var z = left.z - right.z;
        return SafeDouble(System.Math.Sqrt(x * x + y * y + z * z));
    }

    private static double SafeDouble(double value)
    { return double.IsNaN(value) || double.IsInfinity(value) ? 0.0 : value; }

    private static string RequireEnvironment(string name)
    {
        var value = System.Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value)) { throw new System.InvalidOperationException(name + " is required."); }
        return value.Trim();
    }

    private static string RequireSha256Environment(string name)
    {
        var value = RequireEnvironment(name).ToUpperInvariant();
        if (!System.Text.RegularExpressions.Regex.IsMatch(value, "^[0-9A-F]{64}$"))
        { throw new System.InvalidOperationException(name + " must be an uppercase SHA-256 digest."); }
        return value;
    }

    private static string HashFile(string path)
    {
        using (var algorithm = System.Security.Cryptography.SHA256.Create())
        using (var stream = new System.IO.FileStream(path, System.IO.FileMode.Open,
            System.IO.FileAccess.Read, System.IO.FileShare.ReadWrite))
        { return Hex(algorithm.ComputeHash(stream)); }
    }

    private static string Hex(byte[] bytes)
    {
        var builder = new System.Text.StringBuilder(bytes.Length * 2);
        foreach (var item in bytes) { builder.Append(item.ToString("X2")); }
        return builder.ToString();
    }

    private static System.Collections.Generic.Dictionary<string, object> Object(params object[] values)
    {
        var output = new System.Collections.Generic.Dictionary<string, object>();
        for (var index = 0; index < values.Length; index += 2)
        { output.Add((string)values[index], values[index + 1]); }
        return output;
    }

    private static string Json(object value)
    {
        if (value == null) { return "null"; }
        var text = value as string;
        if (text != null) { return "\"" + EscapeJson(text) + "\""; }
        if (value is bool) { return (bool)value ? "true" : "false"; }
        if (value is System.Enum) { return "\"" + EscapeJson(value.ToString()) + "\""; }
        if (value is byte || value is sbyte || value is short || value is ushort ||
            value is int || value is uint || value is long || value is ulong ||
            value is float || value is double || value is decimal)
        { return System.Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture); }
        var dictionary = value as System.Collections.IDictionary;
        if (dictionary != null)
        {
            var fields = new System.Collections.Generic.List<string>();
            foreach (System.Collections.DictionaryEntry entry in dictionary)
            { fields.Add("\"" + EscapeJson((string)entry.Key) + "\":" + Json(entry.Value)); }
            return "{" + string.Join(",", fields.ToArray()) + "}";
        }
        var enumerable = value as System.Collections.IEnumerable;
        if (enumerable != null)
        {
            var items = new System.Collections.Generic.List<string>();
            foreach (var item in enumerable) { items.Add(Json(item)); }
            return "[" + string.Join(",", items.ToArray()) + "]";
        }
        throw new System.InvalidOperationException("Unsupported JSON type: " + value.GetType().FullName);
    }

    private static string EscapeJson(string value)
    {
        var output = new System.Text.StringBuilder();
        foreach (var character in value)
        {
            switch (character)
            {
                case '\\': output.Append("\\\\"); break;
                case '"': output.Append("\\\""); break;
                case '\b': output.Append("\\b"); break;
                case '\f': output.Append("\\f"); break;
                case '\n': output.Append("\\n"); break;
                case '\r': output.Append("\\r"); break;
                case '\t': output.Append("\\t"); break;
                default:
                    if (character < 32) { output.Append("\\u" + ((int)character).ToString("X4")); }
                    else { output.Append(character); }
                    break;
            }
        }
        return output.ToString();
    }
}
