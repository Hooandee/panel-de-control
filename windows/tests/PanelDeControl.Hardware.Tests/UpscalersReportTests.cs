using System.Diagnostics;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Reports;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Reports;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class UpscalersReportTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-upscaler-report-" + Guid.NewGuid().ToString("N"));
    private readonly string game;
    private readonly UpscalerStateStore store;

    public UpscalersReportTests()
    {
        game = Path.Combine(root, "Hooandee", "Game", "Binaries");
        Directory.CreateDirectory(game);
        store = new UpscalerStateStore(Path.Combine(root, "state.json"));
    }

    public void Dispose() => Directory.Delete(root, true);

    [Fact]
    public void SectionNamesWhatIsInstalledAndWhatTheManifestSaysAboutIt()
    {
        File.WriteAllText(Path.Combine(game, "dxgi.dll"), "ours");
        File.WriteAllText(Path.Combine(game, "OptiScaler.log"), "[12:00:00.000] Creating new FSR 3.1 upscaler for D3D12\n");
        var hash = GameFiles.Sha256(Path.Combine(game, "dxgi.dll"));
        Directory.CreateDirectory(Path.Combine(game, GameManifest.Folder));
        File.WriteAllText(
            Path.Combine(game, GameManifest.Folder, GameManifest.FileName),
            "{\"files\": {\"dxgi.dll\": \"" + hash + "\", \"gone.dll\": \"" + hash + "\"}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": []}");
        store.SetInstall("100", new InstalledUpscaler { Build = "fsr-3.1", Engine = "optiscaler", Proxy = "dxgi.dll", Target = game }, 5);
        store.Record(new UpscalerAction(6, "100", "install", "error", "fsr-3.1", "running"));

        var section = UpscalersReportSection.Build(store, new GpuFamilyResult("rdna35", "name"), 18);

        Assert.Equal("rdna35", section["gpu"]!["family"]!.GetValue<string>());
        Assert.Equal("name", section["gpu"]!["source"]!.GetValue<string>());
        Assert.Equal(18, section["catalog_version"]!.GetValue<int>());
        var entry = section["games"]![0]!;
        Assert.Equal(("100", "fsr-3.1", "optiscaler", "dxgi.dll", "running"),
            (entry["appid"]!.GetValue<string>(), entry["build"]!.GetValue<string>(), entry["engine"]!.GetValue<string>(), entry["proxy"]!.GetValue<string>(), entry["last_error"]!.GetValue<string>()));
        var manifest = entry["manifest"]!;
        Assert.Equal((2, 1, 0, 1), (manifest["files"]!.GetValue<int>(), manifest["ok"]!.GetValue<int>(), manifest["changed"]!.GetValue<int>(), manifest["missing"]!.GetValue<int>()));
        Assert.Equal("<game>/gone.dll", manifest["missing_files"]![0]!.GetValue<string>());
        Assert.True(entry["log"]!["present"]!.GetValue<bool>());
        Assert.NotNull(entry["log"]!["modified"]);
        Assert.True(entry["log"]!["upscaler_created"]!.GetValue<bool>());
        Assert.Equal("running", section["journal"]![0]!["error"]!.GetValue<string>());
        Assert.DoesNotContain("pdc-upscaler-report", section.ToJsonString());
        Assert.DoesNotContain("Hooandee", section.ToJsonString());
    }

    [Fact]
    public void SectionCarriesTheIniPanelWroteAgainstTheOneThereNowAndTheHandEdits()
    {
        File.WriteAllText(Path.Combine(game, "OptiScaler.ini"), "[Tweaks]\r\nScale=1.5\r\n\r\n[Log]\r\nLogLevel=2\r\n");
        store.SetInstall("100", new InstalledUpscaler
        {
            Build = "fsr-3.1",
            Engine = "optiscaler",
            Target = game,
            Edited = new[] { new KeyValuePair<string, string>("Tweaks.Scale", "1.5") },
            IniWritten = new IniWritten(7, new[] { new KeyValuePair<string, string>("Log.LogLevel", "3"), new KeyValuePair<string, string>("Tweaks.Scale", "1.5") }),
        }, 5);

        var ini = UpscalersReportSection.Build(store, null, null)["games"]![0]!["ini"]!;

        Assert.Equal("2", ini["values"]!["Log.LogLevel"]!.GetValue<string>());
        Assert.Equal(("changed", 7d), (ini["drift"]!["status"]!.GetValue<string>(), ini["drift"]!["written_at"]!.GetValue<double>()));
        Assert.Equal(("3", "2"), (ini["drift"]!["keys"]!["Log.LogLevel"]!["panel"]!.GetValue<string>(), ini["drift"]!["keys"]!["Log.LogLevel"]!["now"]!.GetValue<string>()));
        Assert.Equal(("Tweaks.Scale", "1.5"), (ini["advanced"]![0]!["key"]!.GetValue<string>(), ini["advanced"]![0]!["value"]!.GetValue<string>()));
        Assert.DoesNotContain("Hooandee", ini.ToJsonString());
    }

    [Fact]
    public void WhatIsNotReadIsNullNeverInvented()
    {
        store.SetInstall("100", new InstalledUpscaler { Build = "fsr-3.1", Target = game }, 5);

        var entry = UpscalersReportSection.Build(store, null, null)["games"]![0]!;

        Assert.False(entry["manifest"]!["present"]!.GetValue<bool>());
        Assert.Null(entry["manifest"]!["files"]);
        Assert.Null(entry["manifest"]!["ok"]);
        Assert.False(entry["log"]!["present"]!.GetValue<bool>());
        Assert.Null(entry["log"]!["upscaler_created"]);
        Assert.Null(entry["last_error"]);
        Assert.Null(UpscalersReportSection.Build(store, null, null)["gpu"]);
    }

    [Fact]
    public void ALogWithoutTheUpscalerLineSaysSo()
    {
        File.WriteAllText(Path.Combine(game, "OptiScaler.log"), "[12:00:00.000] OptiScaler v0.9.4\n");
        store.SetInstall("100", new InstalledUpscaler { Build = "fsr-3.1", Target = game }, 5);

        var log = UpscalersReportSection.Build(store, null, null)["games"]![0]!["log"]!;

        Assert.False(log["upscaler_created"]!.GetValue<bool>());
    }

    [Fact]
    public void TheJournalIsTheLastTwentyOperationsAcrossGames()
    {
        for (var index = 0; index < 15; index++)
        {
            store.Record(new UpscalerAction(index * 2, "1", "install", "done", "a"));
            store.Record(new UpscalerAction(index * 2 + 1, "2", "install", "done", "a"));
        }

        var journal = UpscalersReportSection.Build(store, null, null)["journal"]!.AsArray();

        Assert.Equal(20, journal.Count);
        Assert.Equal(10, journal[0]!["at"]!.GetValue<double>());
        Assert.Equal(29, journal[^1]!["at"]!.GetValue<double>());
    }

    [Fact]
    public void TheBundleCarriesTheSectionWithoutAnyUserPath()
    {
        store.SetInstall("100", new InstalledUpscaler { Build = "fsr-3.1", Target = game }, 5);
        var section = UpscalersReportSection.Build(store, new GpuFamilyResult("rdna35", "pci"), 18);
        section["note"] = game;

        var bundle = ReportBundleBuilder.Build(
            new ReportRequest(ReportKind.Bug, new[] { "upscalers" }, "no se aplica"),
            new ReportEnvironment("0.1.0.0", "rog_ally_x", "ROG Ally X", "ASUS", "RC72", "Windows 11", "10.0.26100"),
            null,
            new JsonObject(),
            new JsonObject(),
            Array.Empty<ReportLogSource>(),
            new ReportRedactor(Path.Combine(root, "Hooandee"), "DESKTOP-TEST"),
            section);

        var text = bundle["state"]!["upscalers"]!.ToJsonString();
        Assert.Contains("\"family\":\"rdna35\"", text);
        Assert.DoesNotContain("Hooandee", text);
    }

    [Fact]
    public void RunningImagesSeesThisProcessUnderItsOwnFolder()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        using var self = Process.GetCurrentProcess();

        var images = RunningImages.Read();

        Assert.Contains(images, path => path.Equals(self.MainModule!.FileName, StringComparison.OrdinalIgnoreCase));
        Assert.True(GameGuards.IsRunningUnder(Path.GetDirectoryName(self.MainModule!.FileName)!, images));
    }
}
