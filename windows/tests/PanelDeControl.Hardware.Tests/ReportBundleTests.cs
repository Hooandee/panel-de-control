using System.IO.Compression;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Reports;
using PanelDeControl.Hardware.Reports;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ReportBundleTests : IDisposable
{
    private readonly string folder = Path.Combine(Path.GetTempPath(), "pdc-report-tests-" + Guid.NewGuid().ToString("N"));
    private readonly ReportRedactor redactor = new(@"C:\Users\Hooandee", "DESKTOP-E112KMI");

    public ReportBundleTests()
    {
        Directory.CreateDirectory(folder);
    }

    public void Dispose()
    {
        Directory.Delete(folder, recursive: true);
    }

    [Fact]
    public void BundleFollowsTheLinuxSchemaAndNamesWindows()
    {
        var bundle = Build(new JsonObject());

        Assert.Equal(6, bundle["schema"]!.GetValue<int>());
        Assert.Equal("panel-de-control", bundle["app"]!.GetValue<string>());
        Assert.Equal("bug", bundle["kind"]!.GetValue<string>());
        Assert.Equal("themes", bundle["categories"]![0]!.GetValue<string>());
        Assert.Equal("windows", bundle["environment"]!["platform"]!["os"]!.GetValue<string>());
        Assert.Equal("ROG Xbox Ally X", bundle["environment"]!["product_name"]!.GetValue<string>());
        Assert.Equal("Hooandee Duo", bundle["state"]!["themes"]!["active"]!.GetValue<string>());
    }

    [Fact]
    public void BundleDropsIdentifiersButKeepsModelWideVersions()
    {
        var machine = new JsonObject
        {
            ["bios"] = new JsonObject { ["bios_version"] = "RC73XA.311", ["serial_number"] = "M3N0LCV12345" },
            ["drivers"] = new JsonArray(new JsonObject
            {
                ["device"] = "ASUS System Control Interface",
                ["driver_version"] = "3.1.38.0",
                ["hardware_id"] = "ACPI\\ASUS2018",
            }),
            ["path"] = @"C:\Users\Hooandee\AppData\Local\PanelDeControl",
        };

        var windows = Build(machine)["windows"]!["machine"]!;

        Assert.Equal("RC73XA.311", windows["bios"]!["bios_version"]!.GetValue<string>());
        Assert.Equal("[redacted]", windows["bios"]!["serial_number"]!.GetValue<string>());
        Assert.Equal("ACPI\\ASUS2018", windows["drivers"]![0]!["hardware_id"]!.GetValue<string>());
        Assert.Equal(@"~\AppData\Local\PanelDeControl", windows["path"]!.GetValue<string>());
    }

    [Fact]
    public void LogsShareOneBudgetAndStartOnAWholeLine()
    {
        var log = Path.Combine(folder, "companion.log");
        File.WriteAllText(log, new string('x', ReportBundleBuilder.MaximumLogBytes) + "\nlast line\n");

        var logs = ReportBundleBuilder.ReadLogs(new[]
        {
            new ReportLogSource("companion.log", log),
            new ReportLogSource("widget-crash.log", Path.Combine(folder, "missing.log")),
        });

        Assert.Equal(2, logs.Count);
        Assert.Equal("last line\n", logs[0]!["text"]!.GetValue<string>());
    }

    [Fact]
    public void MissingLogIsRecordedWithoutText()
    {
        var logs = ReportBundleBuilder.ReadLogs(new[] { new ReportLogSource("widget-crash.log", Path.Combine(folder, "missing.log")) });

        Assert.Equal("FileNotFoundException", logs[0]!["error"]!.GetValue<string>());
    }

    [Fact]
    public void EnvelopeIsTheGzipBundleTheServiceExpects()
    {
        var bundle = Build(new JsonObject());

        var envelope = ReportSender.Envelope(bundle);

        Assert.Equal("gzip", envelope["enc"]!.GetValue<string>());
        Assert.Equal("panel-de-control", envelope["app"]!.GetValue<string>());
        using var gzip = new GZipStream(new MemoryStream(Convert.FromBase64String(envelope["payload"]!.GetValue<string>())), CompressionMode.Decompress);
        using var reader = new StreamReader(gzip, Encoding.UTF8);
        Assert.Equal(bundle.ToJsonString(), reader.ReadToEnd());
    }

    [Theory]
    [InlineData(200, "{\"ok\":true,\"code\":\"PDC-7QK2\",\"issueUrl\":\"https://github.com/x/y/issues/9\"}", ReportStatus.Sent)]
    [InlineData(200, "{\"ok\":true}", ReportStatus.Rejected)]
    [InlineData(500, "not json", ReportStatus.Rejected)]
    public void SuccessNeedsA2xxAndACode(int status, string body, ReportStatus expected)
    {
        var response = ReportSender.Parse(status, body);

        Assert.Equal(expected, response.Status);
        if (expected == ReportStatus.Sent)
        {
            Assert.Equal(("PDC-7QK2", "https://github.com/x/y/issues/9"), (response.Code, response.IssueUrl));
        }
    }

    [Fact]
    public async Task SendsTheEnvelopeAndReturnsTheCode()
    {
        var handler = new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"ok\":true,\"code\":\"PDC-ABCD\"}") });

        var response = await Sender(handler).SendAsync(Build(new JsonObject()), CancellationToken.None);

        Assert.Equal(("PDC-ABCD", ReportStatus.Sent), (response.Code, response.Status));
        Assert.Equal("gzip", JsonNode.Parse(handler.LastBody!)!["enc"]!.GetValue<string>());
        Assert.Empty(Directory.GetFiles(Path.Combine(folder, "offline")));
    }

    [Fact]
    public async Task UnreachableServiceKeepsTheBundleOnDisk()
    {
        var response = await Sender(new StubHandler(_ => throw new HttpRequestException("offline"))).SendAsync(Build(new JsonObject()), CancellationToken.None);

        Assert.Equal((ReportStatus.Saved, "report_service_unreachable"), (response.Status, response.ErrorCode));
        Assert.True(File.Exists(response.SavedPath));
        Assert.Equal("panel-de-control", JsonNode.Parse(File.ReadAllText(response.SavedPath!))!["app"]!.GetValue<string>());
    }

    private JsonObject Build(JsonObject machine)
    {
        return ReportBundleBuilder.Build(
            new ReportRequest(ReportKind.Bug, new[] { "themes" }, "Duo no se aplica"),
            new ReportEnvironment("0.1.0.0", "rog_xbox_ally_x", "ROG Xbox Ally X", "ASUSTeK COMPUTER INC.", "RC73XA", "Microsoft Windows 11 Home", "10.0.26100"),
            new JsonObject { ["active"] = "Hooandee Duo" },
            new JsonObject(),
            machine,
            Array.Empty<ReportLogSource>(),
            redactor);
    }

    private ReportSender Sender(StubHandler handler)
    {
        Directory.CreateDirectory(Path.Combine(folder, "offline"));
        return new ReportSender(new HttpClient(handler), new Uri("https://reports.invalid/api/report"), Path.Combine(folder, "offline"));
    }

    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> respond;

        public StubHandler(Func<HttpRequestMessage, HttpResponseMessage> respond)
        {
            this.respond = respond;
        }

        public string? LastBody { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            LastBody = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
            return respond(request);
        }
    }
}
