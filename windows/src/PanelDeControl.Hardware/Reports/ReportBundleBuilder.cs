using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Reports;

namespace PanelDeControl.Hardware.Reports;

public sealed record ReportLogSource(string Name, string Path);

public sealed record ReportEnvironment(
    string? PackageVersion,
    string? DeviceKey,
    string? ProductName,
    string? Manufacturer,
    string? BoardName,
    string? OperatingSystem,
    string? OperatingSystemBuild);

/// <summary>
/// Builds the bundle the report service stores: the same schema as the Linux plugin, so the service
/// and the download tool read both, plus a <c>windows</c> section with the machine inventory.
/// </summary>
public static class ReportBundleBuilder
{
    public const string App = "panel-de-control";
    public const int Schema = 6;
    public const int MaximumLogBytes = 200_000;

    // Model-wide identifiers that look like serials to the free-text rule but decide which bug applies.
    private static readonly HashSet<string> ModelWideKeys = new(StringComparer.Ordinal)
    {
        "bios_version", "bios_date", "driver_version", "driver_date", "hardware_id", "inf_name", "sku", "build", "version",
    };

    public static JsonObject Build(
        ReportRequest request,
        ReportEnvironment environment,
        JsonNode? themes,
        JsonNode? capabilityInventory,
        JsonNode? machine,
        IEnumerable<ReportLogSource> logs,
        ReportRedactor redactor)
    {
        var bundle = new JsonObject
        {
            ["schema"] = Schema,
            ["app"] = App,
            ["kind"] = request.Kind == ReportKind.Feature ? "feature" : "bug",
            ["categories"] = new JsonArray(request.Categories.Select(category => (JsonNode?)JsonValue.Create(category)).ToArray()),
            ["text"] = request.Text.Length > ReportRequest.MaximumTextLength
                ? request.Text.Substring(0, ReportRequest.MaximumTextLength)
                : request.Text,
            ["environment"] = new JsonObject
            {
                ["platform"] = new JsonObject { ["os"] = "windows" },
                ["plugin_version"] = environment.PackageVersion,
                ["device_key"] = environment.DeviceKey,
                ["product_name"] = environment.ProductName,
                ["product_family"] = environment.Manufacturer,
                ["board_name"] = environment.BoardName,
                ["os"] = environment.OperatingSystem,
                ["kernel"] = environment.OperatingSystemBuild,
            },
            ["capabilities"] = new JsonObject(),
            ["state"] = new JsonObject { ["themes"] = themes },
            ["stores"] = new JsonObject(),
            ["logs"] = ReadLogs(logs),
            ["journal"] = new JsonObject(),
            ["kernel"] = new JsonObject(),
            ["sysfs"] = new JsonObject(),
            ["windows"] = new JsonObject
            {
                ["capability_inventory"] = capabilityInventory,
                ["machine"] = machine,
            },
        };
        return (JsonObject)Redact(bundle, redactor, keepSerialRuns: false)!;
    }

    /// <summary>The newest bytes of each log, sharing one budget, starting on a whole line.</summary>
    public static JsonArray ReadLogs(IEnumerable<ReportLogSource> sources)
    {
        var logs = new JsonArray();
        var budget = MaximumLogBytes;
        foreach (var source in sources)
        {
            if (budget <= 0)
            {
                break;
            }

            string text;
            try
            {
                text = Tail(source.Path, budget);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                logs.Add(new JsonObject { ["name"] = source.Name, ["error"] = exception.GetType().Name });
                continue;
            }

            logs.Add(new JsonObject { ["name"] = source.Name, ["text"] = text });
            budget -= Encoding.UTF8.GetByteCount(text);
        }

        return logs;
    }

    public static JsonNode? Redact(JsonNode? node, ReportRedactor redactor, bool keepSerialRuns)
    {
        switch (node)
        {
            case JsonObject values:
                var redacted = new JsonObject();
                foreach (var (key, value) in values)
                {
                    redacted[key] = ReportRedactor.IsIdentifierKey(key) && value is JsonValue
                        ? "[redacted]"
                        : Redact(value, redactor, keepSerialRuns || ModelWideKeys.Contains(key));
                }

                return redacted;
            case JsonArray items:
                return new JsonArray(items.Select(item => Redact(item, redactor, keepSerialRuns)).ToArray());
            case JsonValue value when value.TryGetValue<string>(out var text):
                return JsonValue.Create(redactor.Redact(text, keepSerialRuns));
            default:
                return node?.DeepClone();
        }
    }

    private static string Tail(string path, int maximumBytes)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        var start = Math.Max(0, stream.Length - maximumBytes);
        stream.Seek(start, SeekOrigin.Begin);
        using var reader = new StreamReader(stream, new UTF8Encoding(false));
        var text = reader.ReadToEnd();
        if (start > 0)
        {
            var newline = text.IndexOf('\n');
            text = newline >= 0 ? text.Substring(newline + 1) : text;
        }

        return text;
    }
}
