// AI-CNC Mastercam 2025 read-only evidence exporter.
//
// Safety contract:
// - Run only against an isolated file-system read-only project copy.
// - Do not call Save/Commit/Delete/Edit/Regenerate/Post or generate G-code.
// - Do not emit source paths, project names, operation names or tool names.
// - Mastercam Operation evidence is not a manufacturing-feature label.

var exporter = new AicncReadonlyMastercamExporter();
exporter.Run();

public sealed class AicncReadonlyMastercamExporter
{
    private const string SchemaVersion = "aicnc.mastercam-readonly-export/0.1";
    private const string ScriptId = "aicnc-mastercam-readonly-exporter/0.1";

    public void Run()
    {
        var outputDirectory = System.Environment.GetEnvironmentVariable(
            "AICNC_MASTERCAM_EXPORT_DIR");
        if (string.IsNullOrWhiteSpace(outputDirectory))
        {
            throw new System.InvalidOperationException(
                "AICNC_MASTERCAM_EXPORT_DIR is required.");
        }

        outputDirectory = System.IO.Path.GetFullPath(outputDirectory);
        if (!System.IO.Directory.Exists(outputDirectory))
        {
            throw new System.InvalidOperationException("The export directory does not exist.");
        }

        var currentFile = Mastercam.IO.FileManager.CurrentFileName;
        if (string.IsNullOrWhiteSpace(currentFile) || !System.IO.File.Exists(currentFile))
        {
            throw new System.InvalidOperationException(
                "A Mastercam project copy must be open before running the exporter.");
        }

        currentFile = System.IO.Path.GetFullPath(currentFile);
        var attributes = System.IO.File.GetAttributes(currentFile);
        if ((attributes & System.IO.FileAttributes.ReadOnly) == 0)
        {
            throw new System.InvalidOperationException(
                "The active Mastercam project is not a file-system read-only copy.");
        }

        var projectSha256 = HashFile(currentFile);
        var expectedSha256 = System.Environment.GetEnvironmentVariable(
            "AICNC_MASTERCAM_EXPECTED_SHA256");
        if (!string.IsNullOrWhiteSpace(expectedSha256) &&
            !string.Equals(projectSha256, expectedSha256.Trim(),
                System.StringComparison.OrdinalIgnoreCase))
        {
            throw new System.InvalidOperationException(
                "The active project hash does not match the isolated-copy request.");
        }

        var discoveryRole = RequireEnvironment("AICNC_MASTERCAM_DISCOVERY_ROLE");
        var catalogManifestSha256 = RequireSha256Environment(
            "AICNC_MASTERCAM_CATALOG_MANIFEST_SHA256");
        var assetId = RequireEnvironment("AICNC_MASTERCAM_ASSET_ID");
        var partId = RequireEnvironment("AICNC_MASTERCAM_PART_ID");
        if (discoveryRole != "a4_non_factory3_semantic_discovery" ||
            !System.Text.RegularExpressions.Regex.IsMatch(assetId, "^asset-[0-9a-f]{16}$") ||
            !System.Text.RegularExpressions.Regex.IsMatch(partId, "^factory-[0-9a-f]{16}$"))
        {
            throw new System.InvalidOperationException(
                "The non-Factory3 A4 catalog authorization is invalid.");
        }

        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var groups = ExportGroups();
        var setupBySignature = new System.Collections.Generic.Dictionary<string, SetupAccumulator>();
        var operations = ExportOperations(setupBySignature);
        var setups = ExportSetups(setupBySignature);
        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        {
            throw new System.InvalidOperationException(
                "The isolated project copy changed while evidence was being exported.");
        }

        var directCount = 0;
        var partialCount = 0;
        var unavailableCount = 0;
        foreach (var operation in operations)
        {
            var selection = (System.Collections.Generic.Dictionary<string, object>)operation["geometry_selection"];
            var status = (string)selection["status"];
            directCount += status == "direct_api" ? 1 : 0;
            partialCount += status == "partial_api" ? 1 : 0;
            unavailableCount += status == "not_exposed_by_current_adapter" ? 1 : 0;
        }

        var extension = System.IO.Path.GetExtension(currentFile).TrimStart('.').ToLowerInvariant();
        if (extension != "mcam" && extension != "mcx")
        {
            extension = "unknown_mastercam";
        }

        var root = Object(
            "schema_version", SchemaVersion,
            "export_id", "mce-" + suffix,
            "project", Object(
                "project_id", "mcproj-" + suffix,
                "project_sha256", projectSha256,
                "copy_sha256_after", copySha256After,
                "source_format", extension,
                "source_copy_mode", "isolated_read_only_copy",
                "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", discoveryRole,
                "catalog_manifest_sha256", catalogManifestSha256,
                "asset_id", assetId,
                "part_id", partId,
                "factory3_excluded", true,
                "issued_by", "aicnc-mastercam-readonly-runner/0.1"),
            "host", Object(
                "product", "Mastercam",
                "file_version", Mastercam.IO.FileManager.MastercamExeVersionName(),
                "product_version", Mastercam.IO.FileManager.MastercamExeProductVersionName(),
                "api_assembly_version", typeof(Mastercam.Database.Operation).Assembly.GetName().Version.ToString(),
                "script_id", ScriptId),
            "policy", Object(
                "source_mutations_permitted", false,
                "mutation_calls_made", false,
                "toolpath_regeneration_permitted", false,
                "postprocessing_permitted", false,
                "gcode_generation_permitted", false,
                "operation_names_anonymized", true,
                "customer_fields_exported", false,
                "factory3_excluded", true,
                "operation_is_feature_label", false),
            "groups", groups,
            "setups", setups,
            "operations", operations,
            "summary", Object(
                "group_count", groups.Count,
                "setup_count", setups.Count,
                "operation_count", operations.Count,
                "direct_selection_count", directCount,
                "partial_selection_count", partialCount,
                "unavailable_selection_count", unavailableCount),
            "training_authorized", false,
            "exported_utc", System.DateTime.UtcNow.ToString(
                "O", System.Globalization.CultureInfo.InvariantCulture));

        var target = System.IO.Path.Combine(outputDirectory, "mce-" + suffix + ".json");
        if (System.IO.File.Exists(target))
        {
            throw new System.InvalidOperationException(
                "The append-only export already exists for this project hash.");
        }

        var temporary = target + ".tmp-" + System.Guid.NewGuid().ToString("N");
        using (var stream = new System.IO.FileStream(
            temporary,
            System.IO.FileMode.CreateNew,
            System.IO.FileAccess.Write,
            System.IO.FileShare.None))
        using (var writer = new System.IO.StreamWriter(
            stream,
            new System.Text.UTF8Encoding(false)))
        {
            writer.Write(Json(root));
        }
        System.IO.File.Move(temporary, target);
    }

    private static System.Collections.Generic.List<object> ExportGroups()
    {
        var output = new System.Collections.Generic.List<object>();
        var groups = Mastercam.Support.SearchManager.GetGroups();
        if (groups == null)
        {
            return output;
        }

        foreach (var group in groups)
        {
            var groupId = GroupId(group.ID);
            string groupType;
            if (group.IsMachineGroup())
            {
                groupType = "machine";
            }
            else if (group.IsToolpathGroup())
            {
                groupType = "toolpath";
            }
            else if (group.IsGeometryGroup())
            {
                groupType = "geometry";
            }
            else
            {
                groupType = "other";
            }

            object parentId = null;
            try
            {
                var parent = group.GetParentGroup();
                if (parent != null && parent.ID >= 0 && parent.ID != group.ID)
                {
                    parentId = GroupId(parent.ID);
                }
            }
            catch
            {
                parentId = null;
            }

            output.Add(Object(
                "group_id", groupId,
                "source_group_id", group.ID,
                "group_type", groupType,
                "name_sha256", HashText(group.Name),
                "parent_group_id", parentId));
        }
        return output;
    }

    private static System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>> ExportOperations(
        System.Collections.Generic.Dictionary<string, SetupAccumulator> setupBySignature)
    {
        var output = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations == null)
        {
            return output;
        }

        for (var index = 0; index < operations.Length; index++)
        {
            var operation = operations[index];
            var sourceId = operation.GetOperationID();
            var operationId = "op-" + sourceId.ToString(
                "D6", System.Globalization.CultureInfo.InvariantCulture);
            Mastercam.Database.OpData operationData = null;
            try
            {
                operationData = Mastercam.Support.SearchManager.GetOperationData(sourceId);
            }
            catch
            {
                operationData = null;
            }

            var planes = ExportPlanes(operation);
            var setupSignature = PlaneSignature(operation);
            SetupAccumulator setup;
            if (!setupBySignature.TryGetValue(setupSignature, out setup))
            {
                setup = new SetupAccumulator(
                    "setup-" + HashText(setupSignature).Substring(0, 16).ToLowerInvariant(),
                    HashText(setupSignature),
                    planes);
                setupBySignature.Add(setupSignature, setup);
            }
            setup.OperationIds.Add(operationId);

            object minimumZ = null;
            object maximumZ = null;
            try
            {
                double min;
                double max;
                if (operation.GetMaxAndMinZ(out max, out min))
                {
                    minimumZ = SafeDouble(min);
                    maximumZ = SafeDouble(max);
                }
            }
            catch
            {
                minimumZ = null;
                maximumZ = null;
            }

            var machineGroupId = operationData != null && operationData.IsValid && operationData.MachineGroupID >= 0
                ? (object)GroupId(operationData.MachineGroupID)
                : null;
            var toolpathGroupId = operationData != null && operationData.IsValid && operationData.ToolpathGroupID >= 0
                ? (object)GroupId(operationData.ToolpathGroupID)
                : null;
            var visible = operationData == null || !operationData.IsValid || operationData.Visible;

            output.Add(Object(
                "operation_id", operationId,
                "source_operation_id", sourceId,
                "sequence", index,
                "operation_type", operation.Type.ToString(),
                "runtime_class", operation.GetType().FullName,
                "display_name_sha256", HashText(operation.Name),
                "machine_group_id", machineGroupId,
                "toolpath_group_id", toolpathGroupId,
                "setup_id", setup.SetupId,
                "planes", planes,
                "state", Object(
                    "dirty", operation.Dirty,
                    "locked", operation.Locked,
                    "posting", operation.Posting,
                    "visible", visible),
                "parameters", Object(
                    "program_number", operation.ProgramNumber,
                    "feed_rate", SafeDouble(operation.FeedRate),
                    "plunge_rate", SafeDouble(operation.PlungeRate),
                    "retract_rate", SafeDouble(operation.RetractRate),
                    "spindle_speed", operation.SpindleSpeed,
                    "minimum_z", minimumZ,
                    "maximum_z", maximumZ),
                "tool", ExportTool(operation.OperationTool),
                "geometry_selection", ExportSelection(operation, sourceId)));
        }
        return output;
    }

    private static System.Collections.Generic.List<object> ExportSetups(
        System.Collections.Generic.Dictionary<string, SetupAccumulator> setupBySignature)
    {
        var output = new System.Collections.Generic.List<object>();
        foreach (var entry in setupBySignature)
        {
            var setup = entry.Value;
            output.Add(Object(
                "setup_id", setup.SetupId,
                "signature_sha256", setup.SignatureSha256,
                "planes", setup.Planes,
                "operation_ids", setup.OperationIds));
        }
        return output;
    }

    private static object ExportTool(Mastercam.Database.Tool tool)
    {
        if (tool == null)
        {
            return null;
        }
        return Object(
            "tool_type", tool.ToolTypeID.ToString(),
            "name_sha256", HashText(tool.Name),
            "tool_number", tool.Number,
            "slot", tool.Slot,
            "is_metric", tool.IsMetric,
            "diameter", SafeDouble(tool.Diameter),
            "corner_radius", SafeDouble(tool.CornerRadius),
            "length", SafeDouble(tool.Length),
            "flute_length", SafeDouble(tool.FluteLength),
            "shoulder_length", SafeDouble(tool.ShoulderLength),
            "tip_angle", SafeDouble(tool.TipAngle),
            "flutes", (int)tool.Flutes);
    }

    private static System.Collections.Generic.Dictionary<string, object> ExportSelection(
        Mastercam.Database.Operation operation,
        int sourceOperationId)
    {
        var chains = new System.Collections.Generic.List<object>();
        var points = new System.Collections.Generic.List<object>();
        var status = "not_exposed_by_current_adapter";

        var chainOperation = operation as Mastercam.Operations.ChainBasedOperation;
        if (chainOperation != null)
        {
            try
            {
                var operationChains = chainOperation.GetChainArray();
                if (operationChains != null)
                {
                    for (var index = 0; index < operationChains.Length; index++)
                    {
                        var chain = operationChains[index];
                        chains.Add(Object(
                            "chain_id", "chain-" + sourceOperationId.ToString("D6") + "-" + index.ToString("D4"),
                            "first_entity_token", "entity-" + chain.FirstEntityId.ToString("D8"),
                            "curves_count", chain.CurvesCount,
                            "is_closed", chain.IsClosed,
                            "is_flat", chain.IsFlat,
                            "perimeter", SafeDouble(chain.Perimeter),
                            "area", SafeDouble(chain.Area),
                            "depth", SafeDouble(chain.Depth)));
                    }
                    status = "direct_api";
                }
            }
            catch
            {
                status = "partial_api";
            }
        }

        var drillOperation = operation as Mastercam.Operations.DrillBasedOperation;
        if (drillOperation != null)
        {
            try
            {
                var drillPoints = drillOperation.DrillPoints;
                var sourceCount = drillPoints == null ? 0 : drillPoints.Count;
                if (drillPoints != null)
                {
                    for (var index = 0; index < drillPoints.Count; index++)
                    {
                        double x;
                        double y;
                        double z;
                        if (TryReadPoint(drillPoints[index], out x, out y, out z))
                        {
                            points.Add(Object(
                                "point_id", "point-" + sourceOperationId.ToString("D6") + "-" + index.ToString("D4"),
                                "coordinates", new object[] { SafeDouble(x), SafeDouble(y), SafeDouble(z) },
                                "coordinate_frame", "mastercam_model"));
                        }
                    }
                }
                status = points.Count == sourceCount ? "direct_api" : "partial_api";
            }
            catch
            {
                status = "partial_api";
            }
        }

        return Object(
            "status", status,
            "chains", chains,
            "drill_points", points,
            "mapping_to_step_faces", "not_established");
    }

    private static bool TryReadPoint(object value, out double x, out double y, out double z)
    {
        x = 0.0;
        y = 0.0;
        z = 0.0;
        if (value == null)
        {
            return false;
        }

        var type = value.GetType();
        var xField = type.GetField("x");
        var yField = type.GetField("y");
        var zField = type.GetField("z");
        if (xField == null || yField == null || zField == null)
        {
            return false;
        }
        try
        {
            x = System.Convert.ToDouble(xField.GetValue(value), System.Globalization.CultureInfo.InvariantCulture);
            y = System.Convert.ToDouble(yField.GetValue(value), System.Globalization.CultureInfo.InvariantCulture);
            z = System.Convert.ToDouble(zField.GetValue(value), System.Globalization.CultureInfo.InvariantCulture);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static System.Collections.Generic.Dictionary<string, object> ExportPlanes(
        Mastercam.Database.Operation operation)
    {
        return Object(
            "wcs", ExportPlane(operation.UseWCS, operation.WCS),
            "tool", ExportPlane(operation.UseToolPlane, operation.ToolPlane),
            "construction", ExportPlane(operation.UseConstructionPlane, operation.ConstructionPlane));
    }

    private static object ExportPlane(bool used, Mastercam.Database.MCView plane)
    {
        if (!used)
        {
            return Object(
                "status", "not_used", "plane_id", null, "name_sha256", null,
                "work_offset_number", null, "origin", null, "matrix", null);
        }
        if (plane == null)
        {
            return Object(
                "status", "unavailable", "plane_id", null, "name_sha256", null,
                "work_offset_number", null, "origin", null, "matrix", null);
        }

        var origin = plane.ViewOrigin;
        var matrix = plane.ViewMatrix;
        return Object(
            "status", "direct_api",
            "plane_id", (int)plane.ViewID,
            "name_sha256", HashText(plane.ViewName),
            "work_offset_number", (int)plane.WorkOffsetNumber,
            "origin", new object[] { SafeDouble(origin.x), SafeDouble(origin.y), SafeDouble(origin.z) },
            "matrix", new object[] {
                new object[] { SafeDouble(matrix.Row1.x), SafeDouble(matrix.Row1.y), SafeDouble(matrix.Row1.z) },
                new object[] { SafeDouble(matrix.Row2.x), SafeDouble(matrix.Row2.y), SafeDouble(matrix.Row2.z) },
                new object[] { SafeDouble(matrix.Row3.x), SafeDouble(matrix.Row3.y), SafeDouble(matrix.Row3.z) }
            });
    }

    private static string PlaneSignature(Mastercam.Database.Operation operation)
    {
        return CanonicalPlane(operation.UseWCS, operation.WCS) + "|" +
            CanonicalPlane(operation.UseToolPlane, operation.ToolPlane) + "|" +
            CanonicalPlane(operation.UseConstructionPlane, operation.ConstructionPlane);
    }

    private static string CanonicalPlane(bool used, Mastercam.Database.MCView plane)
    {
        if (!used)
        {
            return "not-used";
        }
        if (plane == null)
        {
            return "unavailable";
        }
        var origin = plane.ViewOrigin;
        var matrix = plane.ViewMatrix;
        return string.Join(",", new string[] {
            ((int)plane.ViewID).ToString(System.Globalization.CultureInfo.InvariantCulture),
            ((int)plane.WorkOffsetNumber).ToString(System.Globalization.CultureInfo.InvariantCulture),
            Number(origin.x), Number(origin.y), Number(origin.z),
            Number(matrix.Row1.x), Number(matrix.Row1.y), Number(matrix.Row1.z),
            Number(matrix.Row2.x), Number(matrix.Row2.y), Number(matrix.Row2.z),
            Number(matrix.Row3.x), Number(matrix.Row3.y), Number(matrix.Row3.z)
        });
    }

    private static string Number(double value)
    {
        return SafeDouble(value).ToString("R", System.Globalization.CultureInfo.InvariantCulture);
    }

    private static double SafeDouble(double value)
    {
        return double.IsNaN(value) || double.IsInfinity(value) ? 0.0 : value;
    }

    private static string GroupId(int sourceGroupId)
    {
        return "group-" + sourceGroupId.ToString("D6", System.Globalization.CultureInfo.InvariantCulture);
    }

    private static string RequireEnvironment(string name)
    {
        var value = System.Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new System.InvalidOperationException(name + " is required.");
        }
        return value.Trim();
    }

    private static string RequireSha256Environment(string name)
    {
        var value = RequireEnvironment(name).ToUpperInvariant();
        if (!System.Text.RegularExpressions.Regex.IsMatch(value, "^[0-9A-F]{64}$"))
        {
            throw new System.InvalidOperationException(name + " must be an uppercase SHA-256 digest.");
        }
        return value;
    }

    private static string HashFile(string path)
    {
        using (var algorithm = System.Security.Cryptography.SHA256.Create())
        using (var stream = new System.IO.FileStream(
            path, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.ReadWrite))
        {
            return Hex(algorithm.ComputeHash(stream));
        }
    }

    private static string HashText(string value)
    {
        using (var algorithm = System.Security.Cryptography.SHA256.Create())
        {
            return Hex(algorithm.ComputeHash(
                System.Text.Encoding.UTF8.GetBytes(value ?? string.Empty)));
        }
    }

    private static string Hex(byte[] bytes)
    {
        var builder = new System.Text.StringBuilder(bytes.Length * 2);
        foreach (var item in bytes)
        {
            builder.Append(item.ToString("X2", System.Globalization.CultureInfo.InvariantCulture));
        }
        return builder.ToString();
    }

    private static System.Collections.Generic.Dictionary<string, object> Object(params object[] values)
    {
        var output = new System.Collections.Generic.Dictionary<string, object>();
        for (var index = 0; index < values.Length; index += 2)
        {
            output.Add((string)values[index], values[index + 1]);
        }
        return output;
    }

    private static string Json(object value)
    {
        if (value == null)
        {
            return "null";
        }
        var text = value as string;
        if (text != null)
        {
            return "\"" + EscapeJson(text) + "\"";
        }
        if (value is bool)
        {
            return (bool)value ? "true" : "false";
        }
        if (value is System.Enum)
        {
            return "\"" + EscapeJson(value.ToString()) + "\"";
        }
        if (value is byte || value is sbyte || value is short || value is ushort ||
            value is int || value is uint || value is long || value is ulong ||
            value is float || value is double || value is decimal)
        {
            return System.Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture);
        }

        var dictionary = value as System.Collections.IDictionary;
        if (dictionary != null)
        {
            var fields = new System.Collections.Generic.List<string>();
            foreach (System.Collections.DictionaryEntry entry in dictionary)
            {
                fields.Add("\"" + EscapeJson((string)entry.Key) + "\":" + Json(entry.Value));
            }
            return "{" + string.Join(",", fields.ToArray()) + "}";
        }

        var enumerable = value as System.Collections.IEnumerable;
        if (enumerable != null)
        {
            var items = new System.Collections.Generic.List<string>();
            foreach (var item in enumerable)
            {
                items.Add(Json(item));
            }
            return "[" + string.Join(",", items.ToArray()) + "]";
        }

        throw new System.InvalidOperationException(
            "Unsupported JSON value type: " + value.GetType().FullName);
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
                    if (character < 32)
                    {
                        output.Append("\\u" + ((int)character).ToString("X4"));
                    }
                    else
                    {
                        output.Append(character);
                    }
                    break;
            }
        }
        return output.ToString();
    }

    private sealed class SetupAccumulator
    {
        public SetupAccumulator(
            string setupId,
            string signatureSha256,
            System.Collections.Generic.Dictionary<string, object> planes)
        {
            SetupId = setupId;
            SignatureSha256 = signatureSha256;
            Planes = planes;
            OperationIds = new System.Collections.Generic.List<string>();
        }

        public string SetupId { get; private set; }
        public string SignatureSha256 { get; private set; }
        public System.Collections.Generic.Dictionary<string, object> Planes { get; private set; }
        public System.Collections.Generic.List<string> OperationIds { get; private set; }
    }
}
