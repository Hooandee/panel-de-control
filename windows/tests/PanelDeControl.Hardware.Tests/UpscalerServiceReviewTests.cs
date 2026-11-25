using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private const string FreeForm = "my secret note";
    private const string NewFreeForm = "another secret note";

    [Fact]
    public async Task ANewerReleaseWithoutTheInjectorFallsBackToThePinnedOneAndIsNotTriedAgain()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var latest = Latest(ReleaseList(NewerSha));
        var service = Service(prepare: () => PrepareNewerCache(complete: false), latest: latest);

        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(Target(game), "dxgi.dll")));
        var install = new UpscalerStateStore(StatePath).Install("100")!.Install;
        var pinned = Data.Catalog.Asset("optiscaler-0.9.4")!.Sha256;
        Assert.Equal(pinned, install.Components.Single(pair => pair.Key == "optiscaler-0.9.4").Value);
        var origin = install.Origins["optiscaler-0.9.4"];
        Assert.Equal(("pinned", "layout"), (origin.Source, origin.Fallback));

        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal(("pinned", "unresolved"), (
            new UpscalerStateStore(StatePath).Install("100")!.Install.Origins["optiscaler-0.9.4"].Source,
            new UpscalerStateStore(StatePath).Install("100")!.Install.Origins["optiscaler-0.9.4"].Fallback));
    }

    [Fact]
    public async Task TheNewestReleaseIsRecordedAsLatestWithItsTagAndTheReportShowsIt()
    {
        AddGame("100", "Plain");
        var service = Service(prepare: () =>
        {
            PrepareCache();
            PrepareNewerCache();
        }, latest: Latest(ReleaseList(NewerSha)));
        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        var component = (await Send(Service(), UpscalersRequest.Diagnose("100"))).Diagnosis!.Install!.Components.Single(item => item.Id == "optiscaler-0.9.4");

        Assert.Equal(("latest", "v0.9.9"), (component.Source, component.Version));
    }

    [Fact]
    public async Task ARecipeWindowsCannotSatisfyBlocksTheRecipeButNotTheDiagnosis()
    {
        var game = AddGame("1462040", "Remake");
        var recipes = Data.Recipes!;
        var asset = recipes.Dependencies["luma-ff7"].Asset!;
        var kept = recipes.Assets[asset];
        ((IDictionary<string, RecipeAsset>)recipes.Assets).Remove(asset);
        try
        {
            var service = Service(seed: store => store.SetInstall("1462040", Install("fsr-3.1", Target(game)), 5));

            var report = (await Send(service, UpscalersRequest.Diagnose("1462040"))).Diagnosis!;

            Assert.True(report.Recipe!.Blocked);
            Assert.False(report.Recipe.Installable);
            Assert.Equal("recipe_unresolved", report.CurrentSolution!.BlockedReason);
            Assert.NotNull((await Send(service, UpscalersRequest.Compat(new[] { "1462040" }))).Compat!.Games.Single().Preferred);
        }
        finally
        {
            ((IDictionary<string, RecipeAsset>)recipes.Assets)[asset] = kept;
        }
    }

    [Fact]
    public async Task FreeFormValuesOfAnEditedKeyAndUserFoldersNeverLeaveInAReport()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        File.AppendAllText(IniPath(game), "\r\n[Tweaks]\r\nNote=" + FreeForm + "\r\nScale=1.0\r\n");
        var edited = new[] { new KeyValuePair<string, string>("Tweaks.Note", FreeForm), new KeyValuePair<string, string>("Tweaks.Scale", "1.0") };
        Edit("100", install =>
        {
            install.Edited = edited;
            install.IniWritten = IniDiagnostics.Written(File.ReadAllText(IniPath(game)), edited, 5);
        });
        File.WriteAllText(IniPath(game), File.ReadAllText(IniPath(game)).Replace(FreeForm, NewFreeForm).Replace("Scale=1.0", "Scale=2.5"));
        File.WriteAllText(
            Path.Combine(Target(game), "OptiScaler.log"),
            "[12:00:00.000] [W] cannot read C:\\Users\\hoandee\\Documents\\save.dat\n[12:00:01.000] [E] cannot read /home/someone/.config/x\n");
        var service = Service();

        var response = await Send(service, UpscalersRequest.Diagnose("100"));

        var drift = response.Diagnosis!.IniDrift!;
        Assert.Equal(IniDrift.Changed, drift.Status);
        var note = drift.Keys!.Single(change => change.Key == "Tweaks.Note");
        Assert.True(note.ValueOmitted);
        Assert.Equal(("2.5", "1.0"), (drift.Keys!.Single(change => change.Key == "Tweaks.Scale").Now, drift.Keys!.Single(change => change.Key == "Tweaks.Scale").Panel));
        var text = UpscalersWireCodec.SerializeResponse(response);
        Assert.DoesNotContain(FreeForm, text);
        Assert.DoesNotContain(NewFreeForm, text);
        Assert.DoesNotContain("hoandee", text);
        Assert.DoesNotContain("someone", text);
        Assert.Contains(response.Diagnosis.LogExcerpt!, line => line.Contains("cannot read ~\\Documents\\save.dat"));

        var section = UpscalersReportSection.Build(new UpscalerStateStore(StatePath), null, null).ToJsonString();
        Assert.DoesNotContain(FreeForm, section);
        Assert.DoesNotContain(NewFreeForm, section);
    }

    [Fact]
    public async Task AReframeworkConfigureStillRecordsWhatItWroteInTheIni()
    {
        var game = AddGame("1196590", "Village");
        File.WriteAllText(IniPath(game), ImageIni);
        File.WriteAllText(Path.Combine(Target(game), "re2_fw_config.txt"), "[Upscaler]\r\n");
        var service = Service(seed: store => store.SetInstall("1196590", Install("fsr-3.1", Target(game)), 5));

        var response = await Send(service, UpscalersRequest.Configure("1196590", "balanced", null, false, null, null, true));

        Assert.Equal(UpscalersResponseStatus.Ok, response.Status);
        var written = new UpscalerStateStore(StatePath).Install("1196590")!.Install.IniWritten!;
        Assert.Contains(written.Values, pair => pair.Key == "QualityOverrides.QualityRatioBalanced");
    }

    private void PrepareNewerCache(bool complete)
    {
        PrepareCache();
        PrepareNewerCache();
        if (!complete)
        {
            File.Delete(Path.Combine(root, "cache", NewerSha, "unpacked", "OptiScaler.dll"));
            File.Delete(Path.Combine(root, "cache", NewerSha, "unpacked", "OptiScaler.ini"));
        }
    }
}
