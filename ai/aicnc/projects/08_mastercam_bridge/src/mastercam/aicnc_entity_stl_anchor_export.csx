// AI-CNC Mastercam 2026 read-only entity-level STL geometry anchor.
//
// Each existing Solid entity is written to a new ASCII STL in world coordinates
// by explicit entity ID.  The active project must be an isolated read-only copy;
// no selection, database, operation, save, regenerate, post, or source mutation
// call is made.

var exporter = new AicncEntityStlAnchorExporter();
exporter.Run();

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
