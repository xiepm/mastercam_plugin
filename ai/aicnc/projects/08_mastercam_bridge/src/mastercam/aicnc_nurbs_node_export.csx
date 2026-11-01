// AI-CNC Mastercam 2026 read-only native NURBS node sidecar exporter.
//
// NodePoints are exported as Mastercam-native sampled evidence.  They are not
// represented as analytic NURBS control points, weights, or manufacturing
// labels.  The script runs only on an isolated file-system read-only copy.

var exporter = new AicncNurbsNodeSidecarExporter();
exporter.Run();

public sealed class AicncNurbsNodeSidecarExporter
{
    private const string SchemaVersion = "aicnc.mastercam-nurbs-node-geometry/0.1";
    private const string ScriptId = "aicnc-mastercam-nurbs-node-exporter/0.1";

    public void Run()
    {
        var outputDirectory = System.IO.Path.GetFullPath(RequireEnvironment("AICNC_MASTERCAM_EXPORT_DIR"));
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
        if (!string.Equals(projectSha256, RequireSha256Environment("AICNC_MASTERCAM_EXPECTED_SHA256"),
            System.StringComparison.Ordinal))
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
        var sourceNurbsCount = 0;
        var exportedNurbsCount = 0;
        var extractionFailureCount = 0;
        var operationsOutput = new System.Collections.Generic.List<object>();
        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations != null)
        {
            for (var operationIndex = 0; operationIndex < operations.Length; operationIndex++)
            {
                var operation = operations[operationIndex];
                var chainOperation = operation as Mastercam.Operations.ChainBasedOperation;
                if (chainOperation == null) { continue; }
                var operationId = operation.GetOperationID();
                var chainsOutput = new System.Collections.Generic.List<object>();
                var chains = chainOperation.GetChainArray();
                if (chains != null)
                {
                    for (var chainIndex = 0; chainIndex < chains.Length; chainIndex++)
                    {
                        Mastercam.Database.CurveGeometry[] geometry = null;
                        try { geometry = Mastercam.Database.ChainManager.GetGeometryInChain(chains[chainIndex]); }
                        catch { geometry = null; }
                        var count = geometry == null ? 0 : geometry.Length;
                        sourceCurveCount += count;
                        var chainSourceNurbsCount = 0;
                        var curvesOutput = new System.Collections.Generic.List<object>();
                        for (var curveIndex = 0; curveIndex < count; curveIndex++)
                        {
                            var nurbs = geometry[curveIndex] as Mastercam.Curves.NURBSCurveGeometry;
                            if (nurbs == null) { continue; }
                            chainSourceNurbsCount++;
                            sourceNurbsCount++;
                            try
                            {
                                var curveId = "curve-" + operationId.ToString("D6") + "-" +
                                    chainIndex.ToString("D4") + "-" + curveIndex.ToString("D4");
                                var nodes = nurbs.NodePoints;
                                curvesOutput.Add(Object(
                                    "curve_id", curveId,
                                    "runtime_class", nurbs.GetType().FullName,
                                    "start", PointArray(nurbs.EndPoint1),
                                    "end", PointArray(nurbs.EndPoint2),
                                    "mastercam_length", SafeDouble(nurbs.Length),
                                    "degree", (int)nurbs.Degree,
                                    "dimension", (int)nurbs.Dimension,
                                    "is_closed", nurbs.IsClosed,
                                    "is_periodic", nurbs.IsPeriodic,
                                    "is_planar", nurbs.IsPlanar,
                                    "is_uniform", nurbs.IsUniform,
                                    "is_non_rational", nurbs.IsNonRational,
                                    "control_point_count", (int)nurbs.ControlPointsCount,
                                    "knot_count", (int)nurbs.KnotsCount,
                                    "node_point_count", nodes == null ? 0 : nodes.Length,
                                    "node_points", PointArrays(nodes),
                                    "sample_source", "Mastercam.Curves.NURBSCurveGeometry.NodePoints",
                                    "analytic_weights_exported", false,
                                    "coordinate_frame", "mastercam_model"));
                                exportedNurbsCount++;
                            }
                            catch { extractionFailureCount++; }
                        }
                        chainsOutput.Add(Object(
                            "chain_id", "chain-" + operationId.ToString("D6") + "-" + chainIndex.ToString("D4"),
                            "source_curve_count", count,
                            "source_nurbs_count", chainSourceNurbsCount,
                            "exported_nurbs_count", curvesOutput.Count,
                            "curves", curvesOutput));
                    }
                }
                operationsOutput.Add(Object(
                    "operation_id", "op-" + operationId.ToString("D6"),
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
            "node_export_id", "mng-" + suffix,
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
                "operation_is_feature_label", false,
                "node_points_are_analytic_nurbs", false),
            "operations", operationsOutput,
            "summary", Object(
                "source_curve_count", sourceCurveCount,
                "source_nurbs_count", sourceNurbsCount,
                "exported_nurbs_count", exportedNurbsCount,
                "nurbs_extraction_failure_count", extractionFailureCount),
            "automatic_face_binding_authorized", false,
            "training_authorized", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O"));
        var outputPath = System.IO.Path.Combine(outputDirectory, "mng-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        {
            throw new System.InvalidOperationException("The append-only NURBS node sidecar already exists.");
        }
        var temporaryPath = outputPath + ".tmp";
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
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

    private static double SafeDouble(double value)
    { return double.IsNaN(value) || double.IsInfinity(value) ? 0.0 : value; }

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
