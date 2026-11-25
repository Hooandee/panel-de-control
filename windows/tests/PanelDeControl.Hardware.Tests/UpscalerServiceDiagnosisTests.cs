using System.Net;
using System.Text;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private const string NewerSha = "5ee10f7a7e3e3a8b5a3c1d7e9f0b2c4d6e8f1a3b5c7d9e0f2a4b6c8d0e1f3a5b";

    [Fact]
    public async Task DiagnoseReportsTheInstallItsManifestTheVerdictAndTheIniWithoutAbsolutePaths()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        File.WriteAllText(Path.Combine(Target(game), "OptiScaler.log"), "[12:00:00.000] [I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\n[12:00:01.000] [W] something odd\n");
        var service = Service();

        var response = await Send(service, UpscalersRequest.Diagnose("100"));

        var report = response.Diagnosis!;
        Assert.Equal(("100", "Plain", true), (report.AppId, report.Name, report.SteamLookup.Found));
        Assert.Equal(("fsr-3.1", "optiscaler", true), (report.Install!.Build, report.Install.Engine, report.Install.Installed));
        Assert.Equal("performance", report.Install.Options!.Quality);
        Assert.All(report.Install.Components, component => Assert.Matches("^([0-9a-f]{4}-){15}[0-9a-f]{4}$", component.Sha256));
        Assert.True(report.Manifest!.Present);
        Assert.Empty(report.Manifest.Missing!);
        Assert.NotNull(report.LogVerdict);
        Assert.True(report.LogFacts!.Present);
        Assert.Contains(report.LogExcerpt!, line => line.Contains("Creating new fsr31"));
        Assert.Contains(report.Ini!.Values, pair => pair.Key == "Upscalers.Dx12Upscaler");
        Assert.Equal(IniDrift.AsWritten, report.IniDrift!.Status);
        Assert.NotNull(report.ImageSettings);
        Assert.Contains(report.Actions, action => action.Action == "install" && action.State == "done");
        Assert.Contains(report.GameFiles!.Loaders, loader => loader.Path.EndsWith("OptiScaler.ini", StringComparison.Ordinal) && loader.Owner == "panel");
        var text = UpscalersWireCodec.SerializeResponse(response);
        Assert.DoesNotContain(root.Replace("\\", "\\\\"), text);
        Assert.DoesNotContain(Path.GetFileName(root), text);
    }

    [Fact]
    public async Task TheIniPanelLastWroteIsRecordedAndALaterHandEditShowsAsDrift()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        File.AppendAllText(IniPath(game), TweaksIni);
        var service = Service();
        Assert.Equal(UpscalersResponseStatus.Ok, (await Send(service, UpscalersRequest.SetIni("100", "Tweaks.Scale", "1.5", true))).Status);
        Assert.Equal(UpscalersResponseStatus.Ok, (await Send(service, UpscalersRequest.Configure("100", "balanced", null, false, null, null, true))).Status);

        var asWritten = (await Send(service, UpscalersRequest.Diagnose("100"))).Diagnosis!;

        Assert.Equal(IniDrift.AsWritten, asWritten.IniDrift!.Status);
        var edit = Assert.Single(asWritten.Advanced!);
        Assert.Equal(("Tweaks.Scale", "1.5"), (edit.Key, edit.Value));
        var written = new UpscalerStateStore(StatePath).Install("100")!.Install.IniWritten!;
        Assert.Equal(1000, written.At);
        Assert.Contains(written.Values, pair => pair.Key == "QualityOverrides.QualityRatioQuality" && pair.Value == "1.70");

        File.WriteAllText(IniPath(game), IniText.Apply(File.ReadAllText(IniPath(game)),
            new[] { new KeyValuePair<string, string>("Tweaks.Scale", "9.5"), new KeyValuePair<string, string>("Log.LogLevel", "5") }));
        var drifted = (await Send(service, UpscalersRequest.Diagnose("100"))).Diagnosis!.IniDrift!;

        Assert.Equal(IniDrift.Changed, drifted.Status);
        Assert.Equal(new[] { ("Tweaks.Scale", "1.5", "9.5") }, drifted.Keys!.Where(change => change.Key == "Tweaks.Scale").Select(change => (change.Key, change.Panel, change.Now!)));
        Assert.Contains(drifted.Keys!, change => change.Key == "Log.LogLevel" && change.Now == "5");
    }

    [Fact]
    public async Task AnImageSettingWriteMovesTheRecordedIniToo()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        File.WriteAllText(IniPath(game), ImageIni);
        var service = Service();

        var response = await Send(service, UpscalersRequest.SetImage("100", true, 0.5, null, true));

        Assert.Equal((UpscalersResponseStatus.Ok, null), (response.Status, response.ErrorCode));
        Assert.Equal(IniDrift.AsWritten, (await Send(service, UpscalersRequest.Diagnose("100"))).Diagnosis!.IniDrift!.Status);
        Assert.Contains(new UpscalerStateStore(StatePath).Install("100")!.Install.IniWritten!.Values, pair => pair.Key == "Sharpness.OverrideSharpness");
        Assert.True(File.Exists(IniPath(game)));
    }

    [Fact]
    public async Task DiagnoseOfAGameWithoutAnInstallOrWithoutSteamStillAnswers()
    {
        AddGame("100", "Plain");
        var service = Service();

        var plain = (await Send(service, UpscalersRequest.Diagnose("100"))).Diagnosis!;
        var unknown = (await Send(service, UpscalersRequest.Diagnose("999"))).Diagnosis!;

        Assert.Null(plain.Install);
        Assert.Null(plain.IniDrift);
        Assert.True(plain.SteamLookup.Found);
        Assert.False(unknown.SteamLookup.Found);
        Assert.Null(unknown.Name);
        Assert.Null(unknown.GameFiles);
    }

    [Fact]
    public async Task AnInstallWithoutARecordedWriteIsReportedAsUnrecorded()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        Edit("100", install => install.IniWritten = null);

        var drift = (await Send(Service(), UpscalersRequest.Diagnose("100"))).Diagnosis!.IniDrift!;

        Assert.Equal(IniDrift.Unrecorded, drift.Status);
        File.Delete(IniPath(game));
        Assert.True((await Send(Service(), UpscalersRequest.Diagnose("100"))).Diagnosis!.Ini!.Missing);
    }

    [Fact]
    public async Task CompatListsTheInputsOfTheInstalledGamesOnly()
    {
        var shipped = AddGame("100", "Shipped");
        Write(Target(shipped), "nvngx_dlss.dll", "dlss");
        AddGame("200", "Bare");

        var response = await Send(Service(), UpscalersRequest.Compat(new[] { "100", "200", "300", "100" }));

        var games = response.Compat!.Games.ToDictionary(game => game.AppId);
        Assert.True(response.Compat.Complete);
        Assert.Equal(new[] { "100", "200" }, games.Keys.OrderBy(id => id, StringComparer.Ordinal).ToArray());
        Assert.Contains("dlss", games["100"].Inputs);
        Assert.DoesNotContain("dlss", games["200"].Inputs);
        Assert.NotNull(games["100"].Preferred);
    }

    [Fact]
    public async Task ATrackedAssetGoesInAtItsNewestVerifiedReleaseAndTheRecordSaysWhich()
    {
        var game = AddGame("100", "Plain");
        var latest = Latest(ReleaseList(NewerSha));
        var service = Service(prepare: () =>
        {
            PrepareCache();
            PrepareNewerCache();
        }, latest: latest);

        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal("newer optiscaler", File.ReadAllText(Path.Combine(Target(game), "dxgi.dll")));
        var components = new UpscalerStateStore(StatePath).Install("100")!.Install.Components.ToDictionary(pair => pair.Key, pair => pair.Value);
        Assert.Equal(NewerSha, components["optiscaler-0.9.4"]);
        Assert.All(components.Where(pair => pair.Key != "optiscaler-0.9.4"), pair => Assert.NotEqual(NewerSha, pair.Value));
    }

    [Fact]
    public async Task AFailedLookupOrADownloadOfTheNewestFallsBackToTheCatalogsPinnedAsset()
    {
        var offline = AddGame("100", "Offline");
        var service = Service(prepare: PrepareCache, latest: Latest(null));
        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(Target(offline), "dxgi.dll")));

        var game = AddGame("200", "Broken download");
        var latest = Latest(ReleaseList(NewerSha));
        var failing = Service(prepare: PrepareCache, latest: latest, network: new Refusing());
        await failing.HandleAsync(UpscalersRequest.Install("200", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, failing.Job!.State);
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(Target(game), "dxgi.dll")));
        var pinned = Data.Catalog.Asset("optiscaler-0.9.4")!.Sha256;
        Assert.Equal(pinned, new UpscalerStateStore(StatePath).Install("200")!.Install.Components.Single(pair => pair.Key == "optiscaler-0.9.4").Value);
    }

    private void PrepareNewerCache()
    {
        var release = Path.Combine(root, "cache", NewerSha, "unpacked");
        Write(release, ".complete", NewerSha);
        Write(release, "OptiScaler.dll", "newer optiscaler");
        Write(release, "OptiScaler.ini", "[Upscalers]\r\nDx12Upscaler=auto\r\n\r\n[Log]\r\nLogLevel=0\r\n");
        Write(release, "setup_windows.bat", "bat");
        Write(release, "fakenvapi.dll", "fakenvapi");
        Write(release, "D3D12_Optiscaler/D3D12Core.dll", "agility");
    }

    private static string ReleaseList(string sha) =>
        "[{\"tag_name\":\"v0.9.9\",\"published_at\":\"2099-01-01T00:00:00Z\",\"draft\":false,\"prerelease\":false,\"assets\":[{\"name\":\"Optiscaler_0.9.9-final.7z\","
        + "\"size\":1234,\"digest\":\"sha256:" + sha + "\",\"browser_download_url\":\"https://github.com/optiscaler/OptiScaler/releases/download/v0.9.9/Optiscaler_0.9.9-final.7z\"}]}]";

    private LatestReleases Latest(string? answer)
    {
        return new LatestReleases(Data.Catalog.Tracks, Path.Combine(root, "latest-releases.json"), new Refusing { Answer = answer }, () => DateTimeOffset.FromUnixTimeSeconds(2_000_000_000));
    }

    private sealed class Refusing : HttpMessageHandler
    {
        public string? Answer { get; set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (Answer is null || !request.RequestUri!.Host.StartsWith("api.", StringComparison.Ordinal))
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(Answer, Encoding.UTF8, "application/json") });
        }
    }
}
