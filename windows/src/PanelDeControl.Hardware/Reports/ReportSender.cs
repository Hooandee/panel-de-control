using System.IO.Compression;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Reports;

namespace PanelDeControl.Hardware.Reports;

/// <summary>
/// Sends a bundle to the report service the Linux plugin uses (<c>py_modules/report/client.py</c>). It only
/// ever writes: reading a report back is a developer tool on the service, behind its own key.
/// </summary>
public sealed class ReportSender
{
    public const string DefaultServiceUrl = "https://bug-collector-khaki.vercel.app/api/report";
    private const string UserAgent = "panel-de-control-reporter";
    private static readonly TimeSpan SendTimeout = TimeSpan.FromSeconds(20);

    private readonly HttpClient http;
    private readonly Uri serviceUrl;
    private readonly string offlineFolder;

    public ReportSender(HttpClient http, Uri serviceUrl, string offlineFolder)
    {
        this.http = http;
        this.serviceUrl = serviceUrl;
        this.offlineFolder = offlineFolder;
    }

    public static string DefaultOfflineFolder { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "reports");

    public async Task<ReportResponse> SendAsync(JsonObject bundle, CancellationToken cancellationToken)
    {
        string error;
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(SendTimeout);
            using var content = new StringContent(Envelope(bundle).ToJsonString(), Encoding.UTF8, "application/json");
            using var message = new HttpRequestMessage(HttpMethod.Post, serviceUrl) { Content = content };
            message.Headers.UserAgent.Add(new ProductInfoHeaderValue(UserAgent, "1"));
            using var response = await http.SendAsync(message, timeout.Token).ConfigureAwait(false);
            var body = await response.Content.ReadAsStringAsync(timeout.Token).ConfigureAwait(false);
            var parsed = Parse((int)response.StatusCode, body);
            if (parsed.Status == ReportStatus.Sent)
            {
                return parsed;
            }

            error = parsed.ErrorCode ?? "report_service_rejected";
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            error = "report_service_timeout";
        }
        catch (HttpRequestException)
        {
            error = "report_service_unreachable";
        }

        return ReportResponse.Saved(SaveOffline(bundle), error);
    }

    /// <summary>The service's gzip envelope: it decodes and size-checks the bundle itself.</summary>
    public static JsonObject Envelope(JsonObject bundle)
    {
        var raw = Encoding.UTF8.GetBytes(bundle.ToJsonString());
        using var compressed = new MemoryStream();
        using (var gzip = new GZipStream(compressed, CompressionLevel.Optimal, leaveOpen: true))
        {
            gzip.Write(raw, 0, raw.Length);
        }

        return new JsonObject
        {
            ["app"] = bundle["app"]?.DeepClone(),
            ["schema"] = bundle["schema"]?.DeepClone(),
            ["enc"] = "gzip",
            ["payload"] = Convert.ToBase64String(compressed.ToArray()),
        };
    }

    /// <summary>Success needs a 2xx and a code; a malformed body is not a success.</summary>
    public static ReportResponse Parse(int status, string body)
    {
        JsonNode? data = null;
        try
        {
            data = JsonNode.Parse(body);
        }
        catch (JsonException)
        {
        }

        var code = Text(data?["code"]);
        if (status is >= 200 and < 300 && data?["ok"] is JsonValue ok && ok.TryGetValue<bool>(out var accepted) && accepted && !string.IsNullOrWhiteSpace(code))
        {
            return ReportResponse.Sent(code!, Text(data?["issueUrl"]) ?? Text(data?["issue_url"]));
        }

        return ReportResponse.Rejected(status is 413 ? "report_too_large" : status is 429 ? "report_rate_limited" : $"report_service_http_{status}");
    }

    private string? SaveOffline(JsonObject bundle)
    {
        try
        {
            Directory.CreateDirectory(offlineFolder);
            var path = Path.Combine(offlineFolder, $"report-offline-{DateTime.Now:yyyyMMdd-HHmmss}.json");
            File.WriteAllText(path, bundle.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
            return path;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private static string? Text(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue<string>(out var text) ? text : null;
}
