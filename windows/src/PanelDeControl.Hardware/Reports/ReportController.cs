using System.Text.Json.Nodes;
using System.Xml.Linq;
using PanelDeControl.Core.Capabilities;
using PanelDeControl.Core.Reports;
using PanelDeControl.Core.Themes;

namespace PanelDeControl.Hardware.Reports;

public interface IReportController
{
    Task<ReportResponse> SendAsync(ReportRequest request, CancellationToken cancellationToken);
}

public sealed class ReportController : IReportController
{
    private readonly Func<ThemesResponse> themes;
    private readonly Func<CapabilityInventory> capabilityInventory;
    private readonly IDeviceIdentityReader identityReader;
    private readonly ReportSender sender;
    private readonly Func<IReadOnlyList<ReportLogSource>> logs;

    public ReportController(
        Func<ThemesResponse> themes,
        Func<CapabilityInventory> capabilityInventory,
        IDeviceIdentityReader identityReader,
        ReportSender sender,
        Func<IReadOnlyList<ReportLogSource>> logs)
    {
        this.themes = themes;
        this.capabilityInventory = capabilityInventory;
        this.identityReader = identityReader;
        this.sender = sender;
        this.logs = logs;
    }

    public async Task<ReportResponse> SendAsync(ReportRequest request, CancellationToken cancellationToken)
    {
        JsonObject bundle;
        try
        {
            bundle = await Task.Run(() => Build(request), cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            CompanionLog.Write("report.build", exception);
            return ReportResponse.Rejected("report_build_failed");
        }

        var response = await sender.SendAsync(bundle, cancellationToken).ConfigureAwait(false);
        CompanionLog.Write(
            "report." + response.Status.ToString().ToLowerInvariant(),
            response.Status == ReportStatus.Sent
                ? $"{response.Code} {string.Join(",", request.Categories)} {request.Kind}"
                : $"{response.ErrorCode} {(response.SavedPath is null ? "not saved" : "saved offline")}");
        return response;
    }

    private JsonObject Build(ReportRequest request)
    {
        var machine = new JsonObject();
        if (OperatingSystem.IsWindows())
        {
            machine = MachineInventory.Collect();
        }

        var identity = Safe(identityReader.Read);
        var os = machine["os"] as JsonObject;
        var environment = new ReportEnvironment(
            ReadPackageVersion(),
            identity?.Profile?.Key,
            identity?.ProductName,
            identity?.Manufacturer,
            identity?.BoardName,
            Text(os?["caption"]) ?? System.Runtime.InteropServices.RuntimeInformation.OSDescription,
            Text(os?["version"]) ?? Environment.OSVersion.Version.ToString());
        return ReportBundleBuilder.Build(
            request,
            environment,
            Safe(() => JsonNode.Parse(ThemesWireCodec.SerializeResponse(themes()))),
            Safe(() => JsonNode.Parse(CapabilityWireCodec.Serialize(capabilityInventory()))),
            machine,
            logs(),
            new ReportRedactor(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                Environment.MachineName));
    }

    /// <summary>Logs a report carries: the companion's and the widget's crash log.</summary>
    public static IReadOnlyList<ReportLogSource> DefaultLogs()
    {
        var sources = new List<ReportLogSource> { new("companion.log", CompanionLog.FilePath) };
        var packageTemp = Themes.PackageTempFolder.ResolveOrUnavailable();
        var packageRoot = Path.GetDirectoryName(packageTemp);
        if (packageRoot is not null)
        {
            sources.Add(new ReportLogSource("widget-crash.log", Path.Combine(packageRoot, "LocalState", "crash.log")));
        }

        return sources;
    }

    // The companion runs from a folder inside the package; its manifest names the version people install.
    private static string? ReadPackageVersion()
    {
        try
        {
            var folder = new DirectoryInfo(AppContext.BaseDirectory);
            for (var depth = 0; folder is not null && depth < 3; depth++, folder = folder.Parent)
            {
                var manifest = Path.Combine(folder.FullName, "AppxManifest.xml");
                if (File.Exists(manifest))
                {
                    return XDocument.Load(manifest).Root?
                        .Elements().FirstOrDefault(element => element.Name.LocalName == "Identity")?
                        .Attribute("Version")?.Value;
                }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or System.Xml.XmlException)
        {
        }

        return typeof(ReportController).Assembly.GetName().Version?.ToString();
    }

    private static T? Safe<T>(Func<T> read)
        where T : class?
    {
        try
        {
            return read();
        }
        catch (Exception exception)
        {
            CompanionLog.Write("report.collect", exception);
            return null;
        }
    }

    private static string? Text(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;
}
