using System.IO;
using PanelDeControl.Core.Reports;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class ReportsTests
{
    private readonly ReportRedactor redactor = new(@"C:\Users\Hooandee", "DESKTOP-E112KMI");

    [Fact]
    public void RedactsTheUserProfileAnyUserPathAndTheMachineName()
    {
        var text = redactor.Redact(@"loaded C:\Users\Hooandee\AppData\Local\x and c:\users\otra\file on DESKTOP-E112KMI");

        Assert.Equal(@"loaded ~\AppData\Local\x and ~\file on HOST", text);
    }

    [Fact]
    public void KeepsThemeNamesThatContainTheUserName()
    {
        Assert.Equal("Hooandee Duo on", redactor.Redact("Hooandee Duo on"));
    }

    [Fact]
    public void RedactsMacUuidAndSerials()
    {
        var text = redactor.Redact("mac 00:1A:2B:3C:4D:5E guid 1b4e28ba-2fa1-11d2-883f-0016d3cca427 Serial Number: X123 run M3N0LCV12345");

        Assert.Equal("mac [mac] guid [uuid] Serial Number: [serial] run [serial]", text);
    }

    [Fact]
    public void KeepsModelWideVersionsWhenAsked()
    {
        Assert.Equal("RC73XA.311", redactor.Redact("RC73XA.311", keepSerialRuns: true));
        Assert.Equal("ACPI\\ASUS2018", redactor.Redact("ACPI\\ASUS2018", keepSerialRuns: true));
    }

    [Theory]
    [InlineData("serialnumber", true)]
    [InlineData("mac_address", true)]
    [InlineData("hostname", true)]
    [InlineData("user", true)]
    [InlineData("product_name", false)]
    public void RecognizesIdentifierKeys(string key, bool identifier)
    {
        Assert.Equal(identifier, ReportRedactor.IsIdentifierKey(key));
    }

    [Fact]
    public void RequestRoundTripsAndKeepsTheUserText()
    {
        var request = ReportWireCodec.DeserializeRequest(
            ReportWireCodec.SerializeRequest(new ReportRequest(ReportKind.Feature, new[] { "themes" }, "Más opciones\n\"Duo\"")));

        Assert.Equal(ReportKind.Feature, request.Kind);
        Assert.Equal(new[] { "themes" }, request.Categories);
        Assert.Equal("Más opciones\n\"Duo\"", request.Text);
    }

    [Theory]
    [InlineData("themes", "   ", "report_text_required")]
    [InlineData("tdp", "falla", "report_categories_invalid")]
    public void RequestRejectsEmptyTextAndAreasWindowsDoesNotReportYet(string category, string text, string error)
    {
        var exception = Assert.Throws<InvalidDataException>(() => new ReportRequest(ReportKind.Bug, new[] { category }, text).Validate());

        Assert.Equal(error, exception.Message);
    }

    [Fact]
    public void RequestRejectsTextOverTheLimit()
    {
        var request = new ReportRequest(ReportKind.Bug, new[] { "themes" }, new string('a', ReportRequest.MaximumTextLength + 1));

        Assert.Equal("report_text_too_long", Assert.Throws<InvalidDataException>(request.Validate).Message);
    }

    [Fact]
    public void ResponsesNeedTheirCodeOrError()
    {
        var sent = ReportWireCodec.DeserializeResponse(ReportWireCodec.SerializeResponse(ReportResponse.Sent("PDC-7QK2", "https://github.com/x/y/issues/1")));
        var saved = ReportWireCodec.DeserializeResponse(ReportWireCodec.SerializeResponse(ReportResponse.Saved(@"C:\r.json", "report_service_unreachable")));

        Assert.Equal(("PDC-7QK2", ReportStatus.Sent), (sent.Code, sent.Status));
        Assert.Equal((ReportStatus.Saved, "report_service_unreachable"), (saved.Status, saved.ErrorCode));
        Assert.Throws<InvalidDataException>(() => ReportResponse.Sent(" ", null).Validate());
    }
}
