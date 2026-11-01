// AI-CNC Mastercam 2025 NET-Script host probe.
// This script is intentionally read-only with respect to the active Mastercam document.

var app = new AicncHostProbe();
app.Run();

public sealed class AicncHostProbe
{
    public void Run()
    {
        var outputPath = System.Environment.GetEnvironmentVariable("AICNC_MASTERCAM_PROBE_OUTPUT");
        if (string.IsNullOrWhiteSpace(outputPath))
        {
            throw new System.InvalidOperationException(
                "AICNC_MASTERCAM_PROBE_OUTPUT must be an absolute output path.");
        }

        outputPath = System.IO.Path.GetFullPath(outputPath);
        var directory = System.IO.Path.GetDirectoryName(outputPath);
        if (string.IsNullOrWhiteSpace(directory) || !System.IO.Directory.Exists(directory))
        {
            throw new System.InvalidOperationException("The probe output directory does not exist.");
        }

        var payload = string.Format(
            System.Globalization.CultureInfo.InvariantCulture,
            "{{\"schema_version\":\"aicnc.mastercam-host-probe/0.1\",\"mastercam_file_version\":\"{0}\",\"mastercam_product_version\":\"{1}\",\"current_document_present\":{2},\"source_mutations_permitted\":false,\"utc\":\"{3}\"}}",
            Escape(Mastercam.IO.FileManager.MastercamExeVersionName()),
            Escape(Mastercam.IO.FileManager.MastercamExeProductVersionName()),
            string.IsNullOrWhiteSpace(Mastercam.IO.FileManager.CurrentFileName) ? "false" : "true",
            System.DateTime.UtcNow.ToString("O", System.Globalization.CultureInfo.InvariantCulture));

        using (var stream = new System.IO.FileStream(
            outputPath,
            System.IO.FileMode.CreateNew,
            System.IO.FileAccess.Write,
            System.IO.FileShare.None))
        using (var writer = new System.IO.StreamWriter(
            stream,
            new System.Text.UTF8Encoding(false)))
        {
            writer.Write(payload);
        }
    }

    private static string Escape(string value)
    {
        if (value == null)
        {
            return string.Empty;
        }

        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
