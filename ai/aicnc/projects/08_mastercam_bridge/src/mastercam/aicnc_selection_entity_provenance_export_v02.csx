// AI-CNC Mastercam 2026 read-only selection entity/provenance sidecar.
//
// This append-only D-108 prospective adapter records what the public NET-Hook API exposes
// about Chain geometry entities and operation coordinate frames.  It does not
// infer a manufacturing feature, Solid-edge membership, fixture ownership, or
// a CAM-to-STEP transform.

var exporter = new AicncSelectionEntityProvenanceExporter();
exporter.Run();

public sealed class AicncSelectionEntityProvenanceExporter
{
    private const string SchemaVersion = "aicnc.mastercam-selection-entity-provenance/0.2";
    private const string ScriptId = "aicnc-mastercam-selection-entity-provenance-exporter/0.2";

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

        var allGeometry = Mastercam.Support.SearchManager.GetGeometry();
        if (allGeometry == null) { allGeometry = new Mastercam.Database.Geometry[0]; }
        var geometryById = new System.Collections.Generic.Dictionary<int,
            System.Collections.Generic.List<Mastercam.Database.Geometry>>();
        foreach (var geometry in allGeometry)
        {
            if (geometry == null) { continue; }
            try
            {
                var id = geometry.GetEntityID();
                if (!geometryById.ContainsKey(id))
                { geometryById[id] = new System.Collections.Generic.List<Mastercam.Database.Geometry>(); }
                geometryById[id].Add(geometry);
            }
            catch { }
        }
        var solidIds = new System.Collections.Generic.HashSet<int>();
        try
        {
            var solids = Mastercam.Support.SearchManager.GetSolidGeometry();
            if (solids != null) { foreach (var solid in solids) { if (solid != null) { solidIds.Add(solid.GetEntityID()); } } }
        }
        catch { }
        var stockIds = ReadStockEntityIds();

        var sourceCurveCount = 0;
        var exportedCurveCount = 0;
        var entityIdCount = 0;
        var databaseMatchCount = 0;
        var stockMatchCount = 0;
        var operationFrameCount = 0;
        var operationsOutput = new System.Collections.Generic.List<object>();
        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations != null)
        {
            foreach (var operation in operations)
            {
                var chainOperation = operation as Mastercam.Operations.ChainBasedOperation;
                if (chainOperation == null) { continue; }
                var sourceOperationId = operation.GetOperationID();
                var frames = ExportFrames(operation);
                operationFrameCount += CountDirectFrames(frames);
                var chainsOutput = new System.Collections.Generic.List<object>();
                var chains = chainOperation.GetChainArray();
                if (chains != null)
                {
                    for (var chainIndex = 0; chainIndex < chains.Length; chainIndex++)
                    {
                        var chain = chains[chainIndex];
                        var curvesOutput = new System.Collections.Generic.List<object>();
                        Mastercam.Database.CurveGeometry[] curves = null;
                        try { curves = Mastercam.Database.ChainManager.GetGeometryInChain(chain); }
                        catch { curves = null; }
                        var count = curves == null ? 0 : curves.Length;
                        sourceCurveCount += count;
                        for (var curveIndex = 0; curveIndex < count; curveIndex++)
                        {
                            var curve = curves[curveIndex];
                            if (curve == null) { continue; }
                            try
                            {
                                var entityId = curve.GetEntityID();
                                var idAvailable = entityId > 0;
                                if (idAvailable) { entityIdCount++; }
                                System.Collections.Generic.List<Mastercam.Database.Geometry> matches = null;
                                var matchCount = idAvailable && geometryById.TryGetValue(entityId, out matches)
                                    ? matches.Count : 0;
                                if (matchCount > 0) { databaseMatchCount++; }
                                var stockMatch = idAvailable && stockIds.Contains(entityId);
                                if (stockMatch) { stockMatchCount++; }
                                var curveId = "curve-" + sourceOperationId.ToString("D6") + "-" +
                                    chainIndex.ToString("D4") + "-" + curveIndex.ToString("D4");
                                curvesOutput.Add(Object(
                                    "curve_id", curveId,
                                    "entity_token", idAvailable ? (object)("entity-" + entityId.ToString("D8")) : null,
                                    "entity_id_status", idAvailable ? "direct_api" : "unavailable",
                                    "runtime_class", curve.GetType().FullName,
                                    "entity_form", "wireframe_curve",
                                    "level", curve.Level,
                                    "blanked", curve.Blanked,
                                    "selected", curve.Selected,
                                    "color", curve.Color,
                                    "database_geometry_match_count", matchCount,
                                    "database_runtime_classes", RuntimeClasses(matches),
                                    "is_first_chain_entity", idAvailable && entityId == chain.FirstEntityId,
                                    "manufacturing_role", stockMatch ? "stock" : "unknown",
                                    "role_evidence", stockMatch ? "stock_solid_or_mesh_entity_id_match" : "no_direct_public_api_role_match",
                                    "solid_body_id_match", idAvailable && solidIds.Contains(entityId),
                                    "solid_edge_membership_status", "not_exposed_by_public_nethook_adapter",
                                    "stock_entity_id_match", stockMatch,
                                    "fixture_membership_status", "not_exposed_by_public_nethook_adapter",
                                    "check_geometry_membership_status", "not_exposed_by_public_nethook_adapter",
                                    "curve_view", ExportCurveView(curve),
                                    "coordinate_provenance", Object(
                                        "coordinate_source", "Mastercam.Database.ChainManager.GetGeometryInChain",
                                        "stored_frame", "mastercam_database_entity",
                                        "world_transform_status", "not_verified",
                                        "step_transform_status", "not_established")));
                                exportedCurveCount++;
                            }
                            catch { }
                        }
                        chainsOutput.Add(Object(
                            "chain_id", "chain-" + sourceOperationId.ToString("D6") + "-" + chainIndex.ToString("D4"),
                            "first_entity_token", chain.FirstEntityId > 0 ? (object)("entity-" + chain.FirstEntityId.ToString("D8")) : null,
                            "chain_view_number", (int)chain.View,
                            "source_curve_count", count,
                            "exported_curve_count", curvesOutput.Count,
                            "curves", curvesOutput));
                    }
                }
                operationsOutput.Add(Object(
                    "operation_id", "op-" + sourceOperationId.ToString("D6"),
                    "frames", frames,
                    "chains", chainsOutput));
            }
        }
        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The read-only project changed during export."); }
        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var payload = Object(
            "schema_version", SchemaVersion,
            "provenance_export_id", "mcsep-" + suffix,
            "project", Object(
                "project_sha256", projectSha256, "copy_sha256_after", copySha256After,
                "source_copy_mode", "isolated_read_only_copy", "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", role, "catalog_manifest_sha256", catalog,
                "asset_id", assetId, "part_id", partId, "factory3_excluded", true,
                "evidence_classification", "prospective_geometry_gate",
                "retrospective_development_only", false),
            "host", Object(
                "product", "Mastercam", "file_version", Mastercam.IO.FileManager.MastercamExeVersionName(),
                "api_assembly_version", typeof(Mastercam.Database.Operation).Assembly.GetName().Version.ToString(),
                "script_id", ScriptId),
            "policy", Object(
                "source_mutations_permitted", false, "mutation_calls_made", false,
                "operation_names_exported", false, "level_names_exported", false,
                "customer_fields_exported", false, "operation_is_feature_label", false,
                "ownership_inference_permitted", false, "cam_to_step_mapping_claim_permitted", false),
            "database_inventory", Object(
                "geometry_count", allGeometry.Length, "indexed_entity_id_count", geometryById.Count,
                "solid_entity_id_count", solidIds.Count, "stock_reference_entity_id_count", stockIds.Count),
            "operations", operationsOutput,
            "summary", Object(
                "source_curve_count", sourceCurveCount, "exported_curve_count", exportedCurveCount,
                "curve_entity_id_count", entityIdCount, "database_entity_match_count", databaseMatchCount,
                "stock_entity_id_match_count", stockMatchCount,
                "operation_direct_frame_count", operationFrameCount),
            "training_authorized", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O"));
        var outputPath = System.IO.Path.Combine(outputDirectory, "mcsep-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        { throw new System.InvalidOperationException("The append-only provenance sidecar already exists."); }
        var temporaryPath = outputPath + ".tmp";
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
    }

    private static System.Collections.Generic.HashSet<int> ReadStockEntityIds()
    {
        var ids = new System.Collections.Generic.HashSet<int>();
        try
        {
            var data = Mastercam.Support.MillStock.GetStockData();
            if (data != null && data.SolidOrMeshEntID > 0) { ids.Add(data.SolidOrMeshEntID); }
        }
        catch { }
        try
        {
            var operationData = Mastercam.Support.SearchManager.GetOperationData();
            if (operationData != null)
            {
                var groupIds = new System.Collections.Generic.HashSet<int>();
                foreach (var item in operationData)
                { if (item != null && item.IsValid && item.MachineGroupID >= 0) { groupIds.Add(item.MachineGroupID); } }
                foreach (var groupId in groupIds)
                {
                    try
                    {
                        var data = Mastercam.Support.MillStock.GetStockData(groupId);
                        if (data != null && data.SolidOrMeshEntID > 0) { ids.Add(data.SolidOrMeshEntID); }
                    }
                    catch { }
                }
            }
        }
        catch { }
        return ids;
    }

    private static System.Collections.Generic.Dictionary<string, object> ExportFrames(
        Mastercam.Database.Operation operation)
    {
        return Object(
            "wcs", ExportFrame(operation.UseWCS, operation.WCS),
            "tool", ExportFrame(operation.UseToolPlane, operation.ToolPlane),
            "construction", ExportFrame(operation.UseConstructionPlane, operation.ConstructionPlane));
    }

    private static int CountDirectFrames(System.Collections.Generic.Dictionary<string, object> frames)
    {
        var count = 0;
        foreach (var value in frames.Values)
        {
            var frame = value as System.Collections.Generic.Dictionary<string, object>;
            if (frame != null && (string)frame["status"] == "direct_api") { count++; }
        }
        return count;
    }

    private static object ExportFrame(bool used, Mastercam.Database.MCView view)
    {
        if (!used || view == null || !view.Validate())
        { return Object("status", "not_used_or_unavailable", "view_number", null,
            "view_id", null, "work_offset_number", null, "origin", null, "matrix", null); }
        return Object(
            "status", "direct_api", "view_number", (int)view.ViewNumber,
            "view_id", (int)view.ViewID, "work_offset_number", (int)view.WorkOffsetNumber,
            "origin", PointArray(view.ViewOrigin), "matrix", MatrixArray(view.ViewMatrix));
    }

    private static object ExportCurveView(Mastercam.Database.CurveGeometry curve)
    {
        var arc = curve as Mastercam.Curves.ArcGeometry;
        if (arc == null || arc.View == null || !arc.View.Validate())
        { return Object("status", "not_exposed_for_curve_type", "view_number", null,
            "view_id", null, "origin", null, "matrix", null); }
        return Object("status", "direct_api", "view_number", (int)arc.View.ViewNumber,
            "view_id", (int)arc.View.ViewID, "origin", PointArray(arc.View.ViewOrigin),
            "matrix", MatrixArray(arc.View.ViewMatrix));
    }

    private static object[] RuntimeClasses(System.Collections.Generic.List<Mastercam.Database.Geometry> geometries)
    {
        if (geometries == null) { return new object[0]; }
        var names = new System.Collections.Generic.SortedSet<string>();
        foreach (var geometry in geometries) { if (geometry != null) { names.Add(geometry.GetType().FullName); } }
        var output = new object[names.Count]; var index = 0;
        foreach (var name in names) { output[index++] = name; }
        return output;
    }

    private static object[] PointArray(Mastercam.Math.Point3D point)
    { return new object[] { SafeDouble(point.x), SafeDouble(point.y), SafeDouble(point.z) }; }

    private static object[] MatrixArray(Mastercam.Math.Matrix3D matrix)
    { return new object[] {
        new object[] { SafeDouble(matrix.Row1.x), SafeDouble(matrix.Row1.y), SafeDouble(matrix.Row1.z) },
        new object[] { SafeDouble(matrix.Row2.x), SafeDouble(matrix.Row2.y), SafeDouble(matrix.Row2.z) },
        new object[] { SafeDouble(matrix.Row3.x), SafeDouble(matrix.Row3.y), SafeDouble(matrix.Row3.z) } }; }

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
