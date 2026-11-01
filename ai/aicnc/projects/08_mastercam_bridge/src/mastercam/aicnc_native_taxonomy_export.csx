// AI-CNC Mastercam 2026 native taxonomy read-only exporter.
//
// This companion exporter keeps Mastercam Operation semantics separate from
// manufacturing-feature truth.  It probes the documented HoleManager feature
// API and records reflection metadata for FBM/Feature Navigator candidates;
// it never edits, regenerates, posts or saves the active read-only copy.

var exporter = new AicncNativeTaxonomyExporter();
exporter.Run();

public sealed class AicncNativeTaxonomyExporter
{
    private const string SchemaVersion = "aicnc.mastercam-native-taxonomy/0.1";
    private const string ScriptId = "aicnc-mastercam-native-taxonomy-exporter/0.1";

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
        { throw new System.InvalidOperationException("The active Mastercam project is not a file-system read-only copy."); }
        var projectSha256 = HashFile(currentFile);
        var expectedSha256 = RequireSha256Environment("AICNC_MASTERCAM_EXPECTED_SHA256");
        if (!string.Equals(projectSha256, expectedSha256, System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The active project hash does not match the isolated-copy request."); }
        var role = RequireEnvironment("AICNC_MASTERCAM_DISCOVERY_ROLE");
        var catalog = RequireSha256Environment("AICNC_MASTERCAM_CATALOG_MANIFEST_SHA256");
        var assetId = RequireEnvironment("AICNC_MASTERCAM_ASSET_ID");
        var partId = RequireEnvironment("AICNC_MASTERCAM_PART_ID");
        if (role != "a4_non_factory3_semantic_discovery" ||
            !System.Text.RegularExpressions.Regex.IsMatch(assetId, "^asset-[0-9a-f]{16}$") ||
            !System.Text.RegularExpressions.Regex.IsMatch(partId, "^factory-[0-9a-f]{16}$"))
        { throw new System.InvalidOperationException("The A4 authorization is invalid."); }

        var setupBySignature = new System.Collections.Generic.Dictionary<string, SetupAccumulator>();
        var operations = ExportOperations(setupBySignature);
        var setups = ExportSetups(setupBySignature);
        var featureProbe = ProbeNativeFeatures(out var featureTaxonomy);
        var copySha256After = HashFile(currentFile);
        if (!string.Equals(projectSha256, copySha256After, System.StringComparison.Ordinal))
        { throw new System.InvalidOperationException("The read-only project changed during export."); }

        var taxonomyCounts = new System.Collections.Generic.Dictionary<string, TypeAccumulator>();
        foreach (var operation in operations)
        {
            var nativeKey = (string)operation["native_type_key"];
            var operationType = (string)operation["operation_type"];
            var runtimeClass = (string)operation["runtime_class"];
            var key = nativeKey + "\u001f" + operationType + "\u001f" + runtimeClass;
            TypeAccumulator accumulator;
            if (!taxonomyCounts.TryGetValue(key, out accumulator))
            {
                accumulator = new TypeAccumulator(nativeKey, operationType, runtimeClass);
                taxonomyCounts.Add(key, accumulator);
            }
            accumulator.Count++;
        }
        var operationTaxonomy = new System.Collections.Generic.List<object>();
        foreach (var item in taxonomyCounts)
        {
            var value = item.Value;
            operationTaxonomy.Add(Object(
                "native_type_key", value.NativeTypeKey,
                "operation_type", value.OperationType,
                "runtime_class", value.RuntimeClass,
                "occurrence_count", value.Count,
                "evidence_status", "direct_api"));
        }

        var extension = System.IO.Path.GetExtension(currentFile).TrimStart('.').ToLowerInvariant();
        if (extension != "mcam" && extension != "mcx") { extension = "unknown_mastercam"; }
        var suffix = projectSha256.Substring(0, 16).ToLowerInvariant();
        var payload = Object(
            "schema_version", SchemaVersion,
            "export_id", "mcent-" + suffix,
            "project", Object(
                "project_id", "mcproj-" + suffix,
                "project_sha256", projectSha256,
                "copy_sha256_after", copySha256After,
                "source_format", extension,
                "source_copy_mode", "isolated_read_only_copy",
                "source_copy_read_only", true,
                "raw_source_path_disclosed", false),
            "authorization", Object(
                "data_role", role,
                "catalog_manifest_sha256", catalog,
                "asset_id", assetId,
                "part_id", partId,
                "factory3_excluded", true,
                "issued_by", "aicnc-mastercam-native-taxonomy-runner/0.1"),
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
                "operation_is_feature_label", false,
                "feature_instances_are_truth", false,
                "automatic_face_binding_authorized", false,
                "source_project_opened", false),
            "setups", setups,
            "operations", operations,
            "operation_taxonomy", operationTaxonomy,
            "feature_probe", featureProbe,
            "feature_taxonomy", featureTaxonomy,
            "feature_operation_links", new System.Collections.Generic.List<object>(),
            "training_authorized", false,
            "exported_utc", System.DateTime.UtcNow.ToString("O", System.Globalization.CultureInfo.InvariantCulture));

        var outputPath = System.IO.Path.Combine(outputDirectory, "mcent-" + suffix + ".json");
        if (System.IO.File.Exists(outputPath))
        { throw new System.InvalidOperationException("The append-only native taxonomy export already exists."); }
        var temporaryPath = outputPath + ".tmp-" + System.Guid.NewGuid().ToString("N");
        System.IO.File.WriteAllText(temporaryPath, Json(payload) + System.Environment.NewLine,
            new System.Text.UTF8Encoding(false));
        System.IO.File.Move(temporaryPath, outputPath);
    }

    private static System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>> ExportOperations(
        System.Collections.Generic.Dictionary<string, SetupAccumulator> setupBySignature)
    {
        var output = new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, object>>();
        var operations = Mastercam.Support.SearchManager.GetOperations();
        if (operations == null) { return output; }
        for (var index = 0; index < operations.Length; index++)
        {
            var operation = operations[index];
            var sourceId = operation.GetOperationID();
            var operationId = "op-" + sourceId.ToString("D6", System.Globalization.CultureInfo.InvariantCulture);
            Mastercam.Database.OpData operationData = null;
            try { operationData = Mastercam.Support.SearchManager.GetOperationData(sourceId); }
            catch { operationData = null; }
            var setupSignature = PlaneSignature(operation);
            SetupAccumulator setup;
            if (!setupBySignature.TryGetValue(setupSignature, out setup))
            {
                setup = new SetupAccumulator("setup-" + HashText(setupSignature).Substring(0, 16).ToLowerInvariant(), HashText(setupSignature), ExportPlanes(operation));
                setupBySignature.Add(setupSignature, setup);
            }
            setup.OperationIds.Add(operationId);
            object minimumZ = null; object maximumZ = null;
            try { double min; double max; if (operation.GetMaxAndMinZ(out max, out min)) { minimumZ = SafeDouble(min); maximumZ = SafeDouble(max); } }
            catch { minimumZ = null; maximumZ = null; }
            var rawType = operation.Type.ToString();
            var operationType = System.Text.RegularExpressions.Regex.IsMatch(rawType, "^[0-9]+$")
                ? "unknown_native_operation_type" : rawType;
            var machineGroupId = operationData != null && operationData.IsValid && operationData.MachineGroupID >= 0
                ? (object)GroupId(operationData.MachineGroupID) : null;
            var toolpathGroupId = operationData != null && operationData.IsValid && operationData.ToolpathGroupID >= 0
                ? (object)GroupId(operationData.ToolpathGroupID) : null;
            var tool = operation.OperationTool;
            var selection = ExportSelection(operation);
            output.Add(Object(
                "operation_id", operationId,
                "source_operation_id", sourceId,
                "sequence", index,
                "native_type_key", rawType,
                "operation_type", operationType,
                "runtime_class", operation.GetType().FullName,
                "setup_id", setup.SetupId,
                "machine_group_id", machineGroupId,
                "toolpath_group_id", toolpathGroupId,
                "planes", ExportPlanes(operation),
                "tool_type", tool == null ? null : (object)tool.ToolTypeID.ToString(),
                "tool_diameter", tool == null ? null : (object)SafeDouble(tool.Diameter),
                "parameters", Object(
                    "feed_rate", SafeDouble(operation.FeedRate),
                    "plunge_rate", SafeDouble(operation.PlungeRate),
                    "retract_rate", SafeDouble(operation.RetractRate),
                    "spindle_speed", operation.SpindleSpeed,
                    "minimum_z", minimumZ,
                    "maximum_z", maximumZ),
                "selection", selection));
        }
        return output;
    }

    private static System.Collections.Generic.List<object> ExportSetups(
        System.Collections.Generic.Dictionary<string, SetupAccumulator> setupBySignature)
    {
        var output = new System.Collections.Generic.List<object>();
        foreach (var item in setupBySignature.Values)
        { output.Add(Object("setup_id", item.SetupId, "signature_sha256", item.SignatureSha256, "planes", item.Planes, "operation_ids", item.OperationIds)); }
        return output;
    }

    private static System.Collections.Generic.Dictionary<string, object> ExportSelection(Mastercam.Database.Operation operation)
    {
        var chainCount = 0; var drillPointCount = 0; var status = "not_exposed";
        var chainOperation = operation as Mastercam.Operations.ChainBasedOperation;
        if (chainOperation != null)
        {
            try { var chains = chainOperation.GetChainArray(); chainCount = chains == null ? 0 : chains.Length; status = "direct_api"; }
            catch { status = "partial_api"; }
        }
        var drillOperation = operation as Mastercam.Operations.DrillBasedOperation;
        if (drillOperation != null)
        {
            try { var points = drillOperation.DrillPoints; drillPointCount = points == null ? 0 : points.Count; status = "direct_api"; }
            catch { status = "partial_api"; }
        }
        return Object("status", status, "chain_count", chainCount, "drill_point_count", drillPointCount);
    }

    private static System.Collections.Generic.Dictionary<string, object> ProbeNativeFeatures(
        out System.Collections.Generic.List<object> featureTaxonomy)
    {
        featureTaxonomy = new System.Collections.Generic.List<object>();
        var candidates = new System.Collections.Generic.List<string>();
        var assemblies = System.AppDomain.CurrentDomain.GetAssemblies();
        foreach (var assembly in assemblies)
        {
            System.Type[] types;
            try { types = assembly.GetTypes(); }
            catch (System.Reflection.ReflectionTypeLoadException error) { types = error.Types; }
            catch { continue; }
            if (types == null) { continue; }
            foreach (var type in types)
            {
                if (type == null || string.IsNullOrWhiteSpace(type.FullName)) { continue; }
                var name = type.FullName;
                var lower = name.ToLowerInvariant();
                var nativeNamespace = lower.StartsWith("mastercam.") || lower.StartsWith("cnc.") ||
                    lower.StartsWith("fbm") || lower.StartsWith("tp_fbm") || lower.StartsWith("moduleworks.");
                if (!nativeNamespace) { continue; }
                if ((lower.Contains("feature") || lower.Contains("fbm") || lower.Contains("navigator") || lower.Contains("machining")) &&
                    !candidates.Contains(name) && candidates.Count < 120) { candidates.Add(name); }
            }
        }
        var members = new System.Collections.Generic.List<string>();
        foreach (var candidateName in candidates)
        {
            var candidateType = FindType(candidateName);
            if (candidateType == null) { continue; }
            try
            {
                foreach (var property in candidateType.GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static))
                {
                    var lowerProperty = property.Name.ToLowerInvariant();
                    if ((lowerProperty.Contains("feature") || lowerProperty.Contains("face") || lowerProperty.Contains("hole") || lowerProperty.Contains("operation") || lowerProperty.Contains("geometry")) && members.Count < 160)
                    { members.Add(candidateName + "::" + property.Name); }
                }
                foreach (var methodInfo in candidateType.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.DeclaredOnly))
                {
                    var lowerMethod = methodInfo.Name.ToLowerInvariant();
                    if ((lowerMethod.Contains("feature") || lowerMethod.Contains("face") || lowerMethod.Contains("hole") || lowerMethod.Contains("operation") || lowerMethod.Contains("geometry")) && members.Count < 160)
                    { members.Add(candidateName + "::" + methodInfo.Name); }
                }
            }
            catch { }
        }
        var methods = new System.Collections.Generic.List<string>();
        var holeManager = FindType("Mastercam.Solids.HoleManager");
        var method = holeManager == null ? null : FindStaticMethod(holeManager, "GetHolesFromFeatureTree", 2);
        var solids = Mastercam.Support.SearchManager.GetSolidGeometry();
        var invocationSucceeded = false;
        if (method != null && solids != null)
        {
            methods.Add("Mastercam.Solids.HoleManager.GetHolesFromFeatureTree");
            for (var solidIndex = 0; solidIndex < solids.Length; solidIndex++)
            {
                object result;
                try { result = method.Invoke(null, new object[] { solids[solidIndex], 0 }); invocationSucceeded = true; }
                catch { continue; }
                foreach (var hole in Values(result))
                {
                    if (hole == null) { continue; }
                    var featureId = "native-hole-" + solids[solidIndex].GetEntityID().ToString("D8") + "-" + featureTaxonomy.Count.ToString("D4");
                    featureTaxonomy.Add(Object(
                        "feature_id", featureId,
                        "native_feature_class", "hole",
                        "subtype", StringValue(hole, "Type"),
                        "parameters", Object(
                            "is_blind", Value(hole, "IsBlind"),
                            "depth", Value(hole, "Depth"),
                            "edge_type", StringValue(hole, "EdgeType"),
                            "segment_count", Count(ValueRaw(hole, "SegmentPtrs"))),
                        "geometry_references", FaceReferences(hole),
                        "operation_ids", new System.Collections.Generic.List<string>(),
                        "evidence_status", "direct_api",
                        "requires_review", true));
                }
            }
        }
        else if (holeManager != null)
        { methods.Add("Mastercam.Solids.HoleManager.GetHolesFromFeatureTree"); }
        var featureStatus = featureTaxonomy.Count > 0 ? "direct_api" : "not_exposed";
        var note = featureTaxonomy.Count > 0
            ? "Hole definitions were returned through the documented feature-tree API; they remain review-only candidates."
            : (invocationSucceeded ? "Feature-tree API was callable but returned no explicit native feature objects for this project." : "No callable native feature-object collection was observed; candidate type metadata is diagnostic only.");
        return Object(
            "native_feature_object", featureStatus,
            "object_count", featureTaxonomy.Count,
            "api_type_candidates", candidates,
            "api_member_candidates", members,
            "methods_probed", methods,
            "notes", note);
    }

    private static System.Type FindType(string fullName)
    {
        foreach (var assembly in System.AppDomain.CurrentDomain.GetAssemblies())
        { try { var type = assembly.GetType(fullName, false); if (type != null) { return type; } } catch { } }
        return null;
    }

    private static System.Reflection.MethodInfo FindStaticMethod(System.Type type, string name, int parameterCount)
    {
        foreach (var method in type.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static))
        { if (method.Name == name && method.GetParameters().Length == parameterCount) { return method; } }
        return null;
    }

    private static System.Collections.Generic.List<object> Values(object value)
    {
        var output = new System.Collections.Generic.List<object>();
        var enumerable = value as System.Collections.IEnumerable;
        if (enumerable == null) { return output; }
        foreach (var item in enumerable)
        {
            object candidate;
            if (item is System.Collections.DictionaryEntry) { candidate = ((System.Collections.DictionaryEntry)item).Value; }
            else
            {
                var property = item == null ? null : item.GetType().GetProperty("Value");
                candidate = property == null ? item : property.GetValue(item, null);
            }
            var nested = candidate as System.Collections.IEnumerable;
            if (nested != null && !(candidate is string))
            { foreach (var child in Values(candidate)) { output.Add(child); } }
            else { output.Add(candidate); }
        }
        return output;
    }

    private static object Value(object instance, string name)
    {
        if (instance == null) { return null; }
        try
        {
            var property = instance.GetType().GetProperty(name);
            if (property != null) { return JsonSafe(property.GetValue(instance, null)); }
            var method = instance.GetType().GetMethod("Get" + name, System.Type.EmptyTypes);
            return method == null ? null : JsonSafe(method.Invoke(instance, null));
        }
        catch { return null; }
    }

    private static object JsonSafe(object value)
    {
        if (value == null || value is string || value is bool || value is System.Enum || value is int || value is long || value is double || value is float || value is decimal) { return value; }
        if (value is System.Collections.IEnumerable && !(value is string)) { return null; }
        return value.ToString();
    }

    private static string StringValue(object instance, string name)
    { var value = Value(instance, name); return value == null ? null : value.ToString(); }

    private static int Count(object value)
    {
        var enumerable = value as System.Collections.IEnumerable;
        if (enumerable == null) { return 0; }
        var count = 0; foreach (var unused in enumerable) { count++; } return count;
    }

    private static System.Collections.Generic.List<object> FaceReferences(object hole)
    {
        var output = new System.Collections.Generic.List<object>();
        object segments = ValueRaw(hole, "SegmentPtrs");
        if (segments == null) { segments = ValueRaw(hole, "GetSegmentPtrs"); }
        foreach (var segment in Values(segments))
        {
            var faceTags = ValueRaw(segment, "FaceTags");
            foreach (var tag in Values(faceTags))
            { try { output.Add("face-tag-" + System.Convert.ToInt32(tag).ToString("D8")); } catch { } }
        }
        return output;
    }

    private static object ValueRaw(object instance, string name)
    {
        if (instance == null) { return null; }
        try
        {
            var property = instance.GetType().GetProperty(name);
            if (property != null) { return property.GetValue(instance, null); }
            var method = instance.GetType().GetMethod(name, System.Type.EmptyTypes);
            return method == null ? null : method.Invoke(instance, null);
        }
        catch { return null; }
    }

    private static string PlaneSignature(Mastercam.Database.Operation operation)
    { return CanonicalPlane(operation.UseWCS, operation.WCS) + "|" + CanonicalPlane(operation.UseToolPlane, operation.ToolPlane) + "|" + CanonicalPlane(operation.UseConstructionPlane, operation.ConstructionPlane); }

    private static System.Collections.Generic.Dictionary<string, object> ExportPlanes(Mastercam.Database.Operation operation)
    {
        return Object(
            "wcs", ExportPlane(operation.UseWCS, operation.WCS),
            "tool", ExportPlane(operation.UseToolPlane, operation.ToolPlane),
            "construction", ExportPlane(operation.UseConstructionPlane, operation.ConstructionPlane));
    }

    private static object ExportPlane(bool used, Mastercam.Database.MCView plane)
    {
        if (!used) { return Object("status", "not_used", "plane_id", null, "name_sha256", null, "work_offset_number", null, "origin", null, "matrix", null); }
        if (plane == null) { return Object("status", "unavailable", "plane_id", null, "name_sha256", null, "work_offset_number", null, "origin", null, "matrix", null); }
        var origin = plane.ViewOrigin; var matrix = plane.ViewMatrix;
        return Object(
            "status", "direct_api",
            "plane_id", (int)plane.ViewID,
            "name_sha256", HashText(plane.ViewName),
            "work_offset_number", (int)plane.WorkOffsetNumber,
            "origin", new object[] { SafeDouble(origin.x), SafeDouble(origin.y), SafeDouble(origin.z) },
            "matrix", new object[] {
                new object[] { SafeDouble(matrix.Row1.x), SafeDouble(matrix.Row1.y), SafeDouble(matrix.Row1.z) },
                new object[] { SafeDouble(matrix.Row2.x), SafeDouble(matrix.Row2.y), SafeDouble(matrix.Row2.z) },
                new object[] { SafeDouble(matrix.Row3.x), SafeDouble(matrix.Row3.y), SafeDouble(matrix.Row3.z) }});
    }

    private static string CanonicalPlane(bool used, Mastercam.Database.MCView plane)
    {
        if (!used) { return "not-used"; }
        if (plane == null) { return "unavailable"; }
        var origin = plane.ViewOrigin; var matrix = plane.ViewMatrix;
        return string.Join(",", new string[] { ((int)plane.ViewID).ToString(), ((int)plane.WorkOffsetNumber).ToString(), Number(origin.x), Number(origin.y), Number(origin.z), Number(matrix.Row1.x), Number(matrix.Row1.y), Number(matrix.Row1.z), Number(matrix.Row2.x), Number(matrix.Row2.y), Number(matrix.Row2.z), Number(matrix.Row3.x), Number(matrix.Row3.y), Number(matrix.Row3.z) });
    }

    private static string Number(double value) { return SafeDouble(value).ToString("R", System.Globalization.CultureInfo.InvariantCulture); }
    private static double SafeDouble(double value) { return double.IsNaN(value) || double.IsInfinity(value) ? 0.0 : value; }
    private static string GroupId(int sourceGroupId) { return "group-" + sourceGroupId.ToString("D6", System.Globalization.CultureInfo.InvariantCulture); }

    private static string RequireEnvironment(string name)
    { var value = System.Environment.GetEnvironmentVariable(name); if (string.IsNullOrWhiteSpace(value)) { throw new System.InvalidOperationException(name + " is required."); } return value.Trim(); }
    private static string RequireSha256Environment(string name)
    { var value = RequireEnvironment(name).ToUpperInvariant(); if (!System.Text.RegularExpressions.Regex.IsMatch(value, "^[0-9A-F]{64}$")) { throw new System.InvalidOperationException(name + " must be uppercase SHA-256."); } return value; }

    private static string HashFile(string path)
    { using (var algorithm = System.Security.Cryptography.SHA256.Create()) using (var stream = new System.IO.FileStream(path, System.IO.FileMode.Open, System.IO.FileAccess.Read, System.IO.FileShare.ReadWrite)) { return Hex(algorithm.ComputeHash(stream)); } }
    private static string HashText(string value)
    { using (var algorithm = System.Security.Cryptography.SHA256.Create()) { return Hex(algorithm.ComputeHash(System.Text.Encoding.UTF8.GetBytes(value ?? ""))); } }
    private static string Hex(byte[] bytes) { var builder = new System.Text.StringBuilder(bytes.Length * 2); foreach (var item in bytes) { builder.Append(item.ToString("X2")); } return builder.ToString(); }

    private static System.Collections.Generic.Dictionary<string, object> Object(params object[] values)
    { var output = new System.Collections.Generic.Dictionary<string, object>(); for (var index = 0; index < values.Length; index += 2) { output.Add((string)values[index], values[index + 1]); } return output; }
    private static string Json(object value)
    {
        if (value == null) { return "null"; }
        var text = value as string; if (text != null) { return "\"" + EscapeJson(text) + "\""; }
        if (value is bool) { return (bool)value ? "true" : "false"; }
        if (value is System.Enum) { return "\"" + EscapeJson(value.ToString()) + "\""; }
        if (value is byte || value is sbyte || value is short || value is ushort || value is int || value is uint || value is long || value is ulong || value is float || value is double || value is decimal) { return System.Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture); }
        var dictionary = value as System.Collections.IDictionary; if (dictionary != null) { var fields = new System.Collections.Generic.List<string>(); foreach (System.Collections.DictionaryEntry entry in dictionary) { fields.Add("\"" + EscapeJson((string)entry.Key) + "\":" + Json(entry.Value)); } return "{" + string.Join(",", fields.ToArray()) + "}"; }
        var enumerable = value as System.Collections.IEnumerable; if (enumerable != null) { var items = new System.Collections.Generic.List<string>(); foreach (var item in enumerable) { items.Add(Json(item)); } return "[" + string.Join(",", items.ToArray()) + "]"; }
        throw new System.InvalidOperationException("Unsupported JSON value type: " + value.GetType().FullName);
    }
    private static string EscapeJson(string value)
    { var output = new System.Text.StringBuilder(); foreach (var character in value) { switch (character) { case '\\': output.Append("\\\\"); break; case '"': output.Append("\\\""); break; case '\b': output.Append("\\b"); break; case '\f': output.Append("\\f"); break; case '\n': output.Append("\\n"); break; case '\r': output.Append("\\r"); break; case '\t': output.Append("\\t"); break; default: if (character < 32) { output.Append("\\u" + ((int)character).ToString("X4")); } else { output.Append(character); } break; } } return output.ToString(); }

    private sealed class SetupAccumulator
    { public SetupAccumulator(string setupId, string signature, System.Collections.Generic.Dictionary<string, object> planes) { SetupId = setupId; SignatureSha256 = signature; Planes = planes; OperationIds = new System.Collections.Generic.List<string>(); } public string SetupId { get; private set; } public string SignatureSha256 { get; private set; } public System.Collections.Generic.Dictionary<string, object> Planes { get; private set; } public System.Collections.Generic.List<string> OperationIds { get; private set; } }
    private sealed class TypeAccumulator
    { public TypeAccumulator(string nativeTypeKey, string operationType, string runtimeClass) { NativeTypeKey = nativeTypeKey; OperationType = operationType; RuntimeClass = runtimeClass; } public string NativeTypeKey { get; private set; } public string OperationType { get; private set; } public string RuntimeClass { get; private set; } public int Count { get; set; } }
}
