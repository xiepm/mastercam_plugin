// AI-CNC Mastercam 2026 read-only OperationExtents sidecar exporter.

var exporter = new AicncOperationExtentsSidecarExporter();
exporter.Run();

public sealed class AicncOperationExtentsSidecarExporter
{
    private const string SchemaVersion = "aicnc.mastercam-operation-extents/0.1";
    private const string ScriptId = "aicnc-mastercam-operation-extents-exporter/0.1";

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

        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations == null) { operations = new Mastercam.Database.Operation[0]; }
        var records = new System.Collections.Generic.List<object>();
        var validCount = 0;
        var invalidCount = 0;
        var errorCount = 0;
        var aggregateInitialized = false;
        var aggregateMin = new Mastercam.Math.Point3D(0.0, 0.0, 0.0);
        var aggregateMax = new Mastercam.Math.Point3D(0.0, 0.0, 0.0);
        for (var index = 0; index < operations.Length; index++)
        {
            var operationId = operations[index].GetOperationID();
            try
            {
                var extents = Mastercam.Operations.OperationsManager.GetOperationExtents(operationId);
                if (extents == null)
                {
                    invalidCount++;
                    records.Add(EmptyRecord(operationId, "not_returned", null));
                    continue;
                }
                var valid = extents.IsDataValid && Ordered(extents.WorldMin, extents.WorldMax) &&
                    Ordered(extents.WcsMin, extents.WcsMax) && Ordered(extents.TPlaneMin, extents.TPlaneMax);
                if (valid)
                {
                    validCount++;
                    if (!aggregateInitialized)
                    {
                        aggregateMin = extents.WorldMin;
                        aggregateMax = extents.WorldMax;
                        aggregateInitialized = true;
                    }
                    else
                    {
                        aggregateMin = Minimum(aggregateMin, extents.WorldMin);
                        aggregateMax = Maximum(aggregateMax, extents.WorldMax);
                    }
                }
                else { invalidCount++; }
                records.Add(Object(
                    "operation_id", "op-" + operationId.ToString("D6"),
                    "status", valid ? "direct_api" : "invalid_extents",
                    "is_data_valid", extents.IsDataValid,
                    "is_travel_valid", extents.IsTravelValid,
                    "common_wcs_id", extents.CommonWcsID,
                    "common_tplane_id", extents.CommonTPlaneID,
                    "common_wcs_origin_in_view", PointArray(extents.CommonWcsOriginInView),
                    "common_tplane_origin_in_view", PointArray(extents.CommonTPlaneOriginInView),
                    "world", Box(extents.WorldMin, extents.WorldMax),
                    "wcs", Box(extents.WcsMin, extents.WcsMax),
                    "tplane", Box(extents.TPlaneMin, extents.TPlaneMax),
                    "error_type_sha256", null));
            }
            catch (System.Exception error)
            {
                errorCount++;
                records.Add(EmptyRecord(operationId, "api_error", HashText(error.GetType().FullName)));
            }
        }
        var aggregate = aggregateInitialized
            ? Box(aggregateMin, aggregateMax)
            : Object("minimum", null, "maximum", null, "span", null);
        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The read-only project changed during export."); }
        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var payload = Object(
            "schema_version", SchemaVersion,
            "operation_extents_id", "moe-" + suffix,
            "project", Object(
                "project_sha256", projectSha256, "copy_sha256_after", copySha256After,
                "source_copy_mode", "isolated_read_only_copy", "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", role, "catalog_manifest_sha256", catalog,
                "asset_id", assetId, "part_id", partId, "factory3_excluded", true),
            "host", Object(
                "product", "Mastercam",
                "file_version", System.Diagnostics.FileVersionInfo.GetVersionInfo(
                    typeof(Mastercam.IO.FileManager).Assembly.Location).FileVersion,
                "api_assembly_version", typeof(Mastercam.IO.FileManager).Assembly.GetName().Version.ToString(),
                "script_id", ScriptId),
            "policy", Object(
                "source_mutations_permitted", false, "mutation_calls_made", false,
                "geometry_creation_api_used", false, "operation_names_exported", false,
                "customer_fields_exported", false, "operation_is_feature_label", false),
            "operations", records,
            "aggregate_world", aggregate,
            "summary", Object(
                "operation_count", operations.Length, "valid_extents_count", validCount,
                "invalid_extents_count", invalidCount, "api_error_count", errorCount,
                "aggregate_world_valid", aggregateInitialized),
            "coordinate_frame", "mastercam_operation_extents",
            "automatic_face_binding_authorized", false, "training_authorized", false,
            "factory_test_defined", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O"));
        var outputPath = System.IO.Path.Combine(outputDirectory, "moe-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        { throw new System.InvalidOperationException("The append-only OperationExtents sidecar already exists."); }
        var temporaryPath = outputPath + ".tmp";
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
    }

    private static object EmptyRecord(int operationId, string status, string errorHash)
    {
        return Object(
            "operation_id", "op-" + operationId.ToString("D6"), "status", status,
            "is_data_valid", false, "is_travel_valid", false,
            "common_wcs_id", null, "common_tplane_id", null,
            "common_wcs_origin_in_view", null, "common_tplane_origin_in_view", null,
            "world", null, "wcs", null, "tplane", null,
            "error_type_sha256", errorHash);
    }

    private static bool Ordered(Mastercam.Math.Point3D minimum, Mastercam.Math.Point3D maximum)
    {
        return Finite(minimum.x) && Finite(minimum.y) && Finite(minimum.z) &&
            Finite(maximum.x) && Finite(maximum.y) && Finite(maximum.z) &&
            maximum.x >= minimum.x && maximum.y >= minimum.y && maximum.z >= minimum.z;
    }

    private static object Box(Mastercam.Math.Point3D minimum, Mastercam.Math.Point3D maximum)
    {
        return Object("minimum", PointArray(minimum), "maximum", PointArray(maximum),
            "span", new object[] { SafeDouble(maximum.x - minimum.x),
                SafeDouble(maximum.y - minimum.y), SafeDouble(maximum.z - minimum.z) });
    }

    private static Mastercam.Math.Point3D Minimum(Mastercam.Math.Point3D left, Mastercam.Math.Point3D right)
    { return new Mastercam.Math.Point3D(System.Math.Min(left.x, right.x), System.Math.Min(left.y, right.y), System.Math.Min(left.z, right.z)); }

    private static Mastercam.Math.Point3D Maximum(Mastercam.Math.Point3D left, Mastercam.Math.Point3D right)
    { return new Mastercam.Math.Point3D(System.Math.Max(left.x, right.x), System.Math.Max(left.y, right.y), System.Math.Max(left.z, right.z)); }

    private static bool Finite(double value) { return !double.IsNaN(value) && !double.IsInfinity(value); }
    private static double SafeDouble(double value) { return Finite(value) ? value : 0.0; }
    private static object[] PointArray(Mastercam.Math.Point3D point)
    { return new object[] { SafeDouble(point.x), SafeDouble(point.y), SafeDouble(point.z) }; }

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
        using (var stream = new System.IO.FileStream(path, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.ReadWrite))
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
        for (var index = 0; index < values.Length; index += 2) { output.Add((string)values[index], values[index + 1]); }
        return output;
    }
    private static string Json(object value)
    {
        if (value == null) { return "null"; }
        var text = value as string;
        if (text != null) { return "\"" + EscapeJson(text) + "\""; }
        if (value is bool) { return (bool)value ? "true" : "false"; }
        if (value is System.Enum) { return "\"" + EscapeJson(value.ToString()) + "\""; }
        if (value is byte || value is sbyte || value is short || value is ushort || value is int || value is uint ||
            value is long || value is ulong || value is float || value is double || value is decimal)
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
                case '\\': builder.Append("\\\\"); break; case '"': builder.Append("\\\""); break;
                case '\b': builder.Append("\\b"); break; case '\f': builder.Append("\\f"); break;
                case '\n': builder.Append("\\n"); break; case '\r': builder.Append("\\r"); break;
                case '\t': builder.Append("\\t"); break;
                default: if (character < 32) { builder.Append("\\u" + ((int)character).ToString("X4")); } else { builder.Append(character); } break;
            }
        }
        return builder.ToString();
    }
}
