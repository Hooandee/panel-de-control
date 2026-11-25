using System.IO.Compression;
using System.Text;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using static PanelDeControl.TestSupport.TestTree;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private const string HelixBuild = "hlx-fsr4";
    private const string GameFsr = "game fsr 3.1";

    private static UpscalerAsset HelixArchive => Data.Catalog.Asset(Data.Catalog.Build(HelixBuild)!.Archive)!;

    private static UpscalerAsset PythonArchive => Data.Catalog.Asset(Data.Catalog.Build(HelixBuild)!.AssetsFor("windows").Single())!;

    private HelixSr NewHelix(IHelixProcess process) => new(Path.Combine(root, "upscalers"), "HelixSR-3.2.0", process);

    private void SeedHelixRuntime(HelixSr helix)
    {
        Write(helix.PythonFolder, "python.exe", "python");
        Write(helix.PythonFolder, HelixRelease.Complete, PythonArchive.Sha256);
        var release = Path.Combine(helix.ReleasesFolder, "HelixSR-3.2.0");
        Write(release, "setup/helixsr_bridge.py", "bridge");
        Write(release, HelixRelease.Complete, HelixArchive.Sha256);
    }

    private void SeedHelixArchives(string[]? python = null, string[]? release = null)
    {
        Zip(PythonArchive, python ?? new[] { "python.exe", "python314.dll", "python314._pth" });
        Zip(HelixArchive, release ?? new[] { "HelixSR-3.2.0/setup/helixsr_bridge.py", "HelixSR-3.2.0/LICENSE", "HelixSR-3.2.0/HLX-FSR4/a.dll", "HelixSR-3.2.0/setup/", "README.md", "Other/x.txt" });
    }

    private void Zip(UpscalerAsset asset, string[] entries)
    {
        var path = Path.Combine(root, "cache", asset.Sha256, asset.FileName);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
        foreach (var name in entries)
        {
            using var writer = new StreamWriter(archive.CreateEntry(name).Open(), new UTF8Encoding(false));
            writer.Write("content of " + name);
        }
    }

    private async Task<UpscalerJobStatus> RunInstallAsync(UpscalerService service, string appId = "100", string build = HelixBuild)
    {
        var started = await service.HandleAsync(UpscalersRequest.Install(appId, build, null, null, true), CancellationToken.None);
        Assert.Equal(UpscalersResponseStatus.Ok, started.Status);
        await RunDeferredAsync();
        return service.Job!;
    }

    private async Task<UpscalerJobStatus> RunUninstallAsync(UpscalerService service, string appId = "100")
    {
        var started = await service.HandleAsync(UpscalersRequest.Uninstall(appId, true), CancellationToken.None);
        Assert.Equal(UpscalersResponseStatus.Ok, started.Status);
        await RunDeferredAsync();
        return service.Job!;
    }

    private async Task<(string Game, FakeHelixBridge Bridge, HelixSr Helix)> InstalledHelixAsync()
    {
        var game = AddGame("100", "Plain");
        var bridge = new FakeHelixBridge();
        var helix = NewHelix(bridge);
        SeedHelixArchives();
        Assert.Equal(UpscalerJobStates.Done, (await RunInstallAsync(Service(helix: helix))).State);
        return (game, bridge, helix);
    }

    [Fact]
    public async Task HelixIsOfferedOnlyWhenTheGameCarriesFsr31AndHelixIsAvailable()
    {
        AddGame("100", "WithFsr");
        var plain = AddGame("200", "NoFsr");
        File.Delete(Path.Combine(Target(plain), "amd_fidelityfx_dx12.dll"));

        var offered = (await Service().HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!.Builds.Single(build => build.Id == HelixBuild);
        var withoutFsr = (await Service().HandleAsync(UpscalersRequest.Game("200"), CancellationToken.None)).Game!.Builds;
        var withoutHelix = (await Service(noHelix: true).HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!.Builds;

        Assert.Equal(("helixsr", "helixsr", "FSR 4"), (offered.Engine, offered.Family, offered.Version));
        Assert.Equal(HelixArchive.Size + PythonArchive.Size, offered.DownloadBytes);
        Assert.DoesNotContain(withoutFsr, build => build.Id == HelixBuild);
        Assert.DoesNotContain(withoutHelix, build => build.Id == HelixBuild);
    }

    [Fact]
    public async Task WithoutHelixTheBuildIsRefusedAsUnsupported()
    {
        AddGame("100", "Plain");
        var service = Service(noHelix: true);

        var response = await service.HandleAsync(UpscalersRequest.Install("100", HelixBuild, null, null, true), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, "engine_unsupported"), (response.Status, response.ErrorCode));
        Assert.Null(service.Job);
    }

    [Fact]
    public async Task AGameWithoutFsr31IsRefusedBeforeAnyJob()
    {
        var game = AddGame("100", "NoFsr");
        File.Delete(Path.Combine(Target(game), "amd_fidelityfx_dx12.dll"));
        var service = Service();

        var response = await service.HandleAsync(UpscalersRequest.Install("100", HelixBuild, null, null, true), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, "helixsr_no_fsr"), (response.Status, response.ErrorCode));
        Assert.Null(service.Job);
    }

    [Fact]
    public async Task InstallDownloadsPythonAndTheReleaseOnceThenRunsTheOfficialBridge()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var bridge = new FakeHelixBridge();
        var helix = NewHelix(bridge);
        var stages = new List<string>();
        SeedHelixArchives();
        var service = Service(helix: helix);
        bridge.Observe = _ => stages.Add(service.Job!.Stage);

        var job = await RunInstallAsync(service);

        Assert.Equal((UpscalerJobStates.Done, "done", null), (job.State, job.Stage, job.Error));
        Assert.Equal(new[] { "install" }, stages);
        Assert.True(helix.PythonIs(PythonArchive.Sha256));
        Assert.True(helix.ReleaseReady);
        Assert.Equal(HelixArchive.Sha256, helix.Digest);
        var release = Path.Combine(helix.ReleasesFolder, "HelixSR-3.2.0");
        Assert.Equal("HelixSR-3.2.0", File.ReadAllText(Path.Combine(helix.ReleasesFolder, "current")));
        Assert.True(File.Exists(Path.Combine(release, "LICENSE")));
        Assert.True(File.Exists(Path.Combine(release, "HLX-FSR4", "a.dll")));
        Assert.False(File.Exists(Path.Combine(helix.ReleasesFolder, "README.md")));
        Assert.False(File.Exists(Path.Combine(release, "README.md")));
        Assert.False(Directory.Exists(Path.Combine(root, "cache", HelixArchive.Sha256)));
        Assert.False(Directory.Exists(Path.Combine(root, "cache", PythonArchive.Sha256)));
        Assert.Empty(Directory.GetDirectories(helix.ReleasesFolder, ".*"));

        var call = Assert.Single(bridge.Calls);
        Assert.Equal(Path.Combine(helix.PythonFolder, "python.exe"), call.Executable);
        Assert.Equal(new[] { "-X", "utf8", Path.Combine(release, "setup", "helixsr_bridge.py"), release, "install", "--game", Path.GetFullPath(game), "--way", "fsr" }, call.Arguments);
        Assert.Equal((release, TimeSpan.FromSeconds(180)), (call.WorkingDirectory, call.Timeout));

        Assert.Equal(FakeHelixBridge.Drop, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
        Assert.Equal(GameFsr, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Backup)));
        var marker = Path.Combine(Target(game), ".pdc-upscaler", "helixsr.json");
        Assert.Contains("\"way\": \"fsr\"", File.ReadAllText(marker));
        Assert.NotEqual(before, Snapshot(game));
    }

    [Fact]
    public async Task TheInstallIsRecordedLikeLinuxAndShownOnTheGamePage()
    {
        var (game, _, _) = await InstalledHelixAsync();
        var stored = new UpscalerStateStore(StatePath).Install("100")!;

        Assert.Equal(("helixsr", "fsr", HelixBuild, "", Path.GetFullPath(Target(game))), (stored.Install.Engine, stored.Install.Way, stored.Install.Build, stored.Install.Proxy, Path.GetFullPath(stored.Install.Target)));
        Assert.Equal(Path.GetFullPath(Target(game)), stored.Install.ExeFolder);
        Assert.Equal(Path.Combine(Path.GetFullPath(Target(game)), "helixsr.log"), stored.Install.Log);
        Assert.Equal(Path.Combine(Path.GetFullPath(Target(game)), "helixsr-install.json"), stored.Install.HelixFile);
        Assert.Equal("Binaries/Win64/Game.exe", stored.Install.Exe);
        Assert.Contains("\"engine\": \"helixsr\"", File.ReadAllText(StatePath));
        Assert.Contains("\"helix_file\"", File.ReadAllText(StatePath));
        Assert.Equal("pending", new UpscalerStateStore(StatePath).History("100").Single().Result);
        Assert.Null(new UpscalerStateStore(StatePath).History("100").Single().Proxy);

        var detail = (await Service().HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;

        Assert.Equal(UpscalerGameStates.Installed, detail.Game.State);
        Assert.Equal(("HLX FSR 4", UpscalerGameStates.Installed, "not_run"), (detail.Install!.Label, detail.Install.Status, detail.Install.Verdict));
        Assert.Null(detail.Foreign);
        Assert.Equal("HLX FSR 4", (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single().Label);
    }

    [Fact]
    public async Task TheVerdictComesFromHelixSrsOwnLogAfterTheInstall()
    {
        var (game, _, _) = await InstalledHelixAsync();
        var storage = Path.Combine(Target(game), "_storage_");
        Write(storage, "amd_fidelityfx_upscaler_dx12.dll", "provider");
        Write(storage, "HLX_FSR.log", "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x720, max render 1280x720\n");

        var detail = (await Service().HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;

        Assert.Equal(("active", "HLX FSR 4"), (detail.Install!.Verdict, detail.Install.Observed));
        Assert.Equal("active", detail.History!.Single().Result);
        Assert.Equal("active", new UpscalerStateStore(StatePath).History("100").Single().Result);
    }

    [Fact]
    public async Task ASecondInstallReusesWhatIsUnpackedAndDownloadsNothing()
    {
        var game = AddGame("100", "Plain");
        var bridge = new FakeHelixBridge();
        var helix = NewHelix(bridge);
        SeedHelixRuntime(helix);

        var job = await RunInstallAsync(Service(helix: helix));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.Equal(FakeHelixBridge.Drop, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
    }

    [Fact]
    public async Task APythonOfAnotherDigestIsReplacedFromTheCatalogsAsset()
    {
        AddGame("100", "Plain");
        var bridge = new FakeHelixBridge();
        var helix = NewHelix(bridge);
        SeedHelixRuntime(helix);
        Write(helix.PythonFolder, HelixRelease.Complete, new string('0', 64));
        Write(helix.PythonFolder, "old.txt", "old");
        SeedHelixArchives();

        Assert.Equal(UpscalerJobStates.Done, (await RunInstallAsync(Service(helix: helix))).State);

        Assert.True(helix.PythonIs(PythonArchive.Sha256));
        Assert.False(File.Exists(Path.Combine(helix.PythonFolder, "old.txt")));
        Assert.True(File.Exists(Path.Combine(helix.PythonFolder, "python314.dll")));
    }

    [Fact]
    public async Task UninstallRunsTheBridgeAndLeavesTheGameExactlyAsItWas()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var bridge = new FakeHelixBridge();
        var helix = NewHelix(bridge);
        SeedHelixArchives();
        await RunInstallAsync(Service(helix: helix));
        File.WriteAllText(Path.Combine(Target(game), "helixsr.log"), "log");
        File.WriteAllText(Path.Combine(Target(game), "HLX_FSR.log"), "runtime");

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Done, null), (job.State, job.Error));
        var call = bridge.Calls.Last();
        var release = Path.Combine(helix.ReleasesFolder, "HelixSR-3.2.0");
        Assert.Equal(new[] { "-X", "utf8", Path.Combine(release, "setup", "helixsr_bridge.py"), release, "remove", "--game", Path.GetFullPath(game) }, call.Arguments);
        Assert.Equal(before, Snapshot(game));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
        Assert.Equal(UpscalerGameStates.None, (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single().State);
    }

    [Fact]
    public async Task AGameUpdateThatReplacedHelixsDllIsKeptWhenTheBridgeSaysNothingIsInstalled()
    {
        var (game, bridge, helix) = await InstalledHelixAsync();
        File.WriteAllText(Path.Combine(Target(game), FakeHelixBridge.Library), "the update's new FSR");
        File.WriteAllText(Path.Combine(Target(game), FakeHelixBridge.Backup), "old backup");

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.Equal("remove", bridge.Calls.Last().Arguments[4]);
        Assert.Equal("the update's new FSR", File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
        Assert.False(File.Exists(Path.Combine(Target(game), "helixsr-install.json")));
        Assert.False(Directory.Exists(Path.Combine(Target(game), ".pdc-upscaler")));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task WithoutHelixSrsRecordTheBridgeStillDecidesAndNothingLeftIsFine()
    {
        var (game, _, helix) = await InstalledHelixAsync();
        File.Delete(Path.Combine(Target(game), "helixsr-install.json"));

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.False(Directory.Exists(Path.Combine(Target(game), ".pdc-upscaler")));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task WhenTheReleaseIsGoneTheRecordedSwapsAreUndoneByHand()
    {
        var (game, bridge, helix) = await InstalledHelixAsync();
        var calls = bridge.Calls.Count;
        Directory.Delete(helix.ReleasesFolder, true);

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.Equal(calls, bridge.Calls.Count);
        Assert.Equal(GameFsr, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
        Assert.False(File.Exists(Path.Combine(Target(game), FakeHelixBridge.Backup)));
        Assert.False(File.Exists(Path.Combine(Target(game), "helixsr-install.json")));
    }

    [Fact]
    public async Task ARemovalByHandThatCannotRestoreTheGamesFileFailsAndKeepsTheInstall()
    {
        var (game, _, helix) = await InstalledHelixAsync();
        Directory.Delete(helix.ReleasesFolder, true);
        File.Delete(Path.Combine(Target(game), FakeHelixBridge.Backup));

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed"), (job.State, job.Error));
        Assert.NotNull(new UpscalerStateStore(StatePath).Install("100"));
        Assert.True(File.Exists(Path.Combine(Target(game), "helixsr-install.json")));
    }

    [Fact]
    public async Task ABridgeFailureOnUninstallKeepsTheInstallAndSaysWhy()
    {
        var (game, bridge, helix) = await InstalledHelixAsync();
        bridge.Answer = _ => FakeHelixBridge.Fail("could not write the DLL");

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed", "could not write the DLL"), (job.State, job.Error, job.Detail));
        Assert.NotNull(new UpscalerStateStore(StatePath).Install("100"));
        Assert.True(File.Exists(Path.Combine(Target(game), ".pdc-upscaler", "helixsr.json")));
    }

    [Fact]
    public async Task ABridgeThatReportsAFailureLeavesNothingBehind()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var bridge = new FakeHelixBridge { Answer = _ => FakeHelixBridge.Fail("no write access") };
        SeedHelixArchives();
        var service = Service(helix: NewHelix(bridge));

        var job = await RunInstallAsync(service);

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed", "no write access"), (job.State, job.Error, job.Detail));
        Assert.Equal(before, Snapshot(game));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
        Assert.Equal(new[] { "started", "error" }, new UpscalerStateStore(StatePath).Actions("100").Select(action => action.State));
    }

    [Theory]
    [InlineData(typeof(TimeoutException))]
    [InlineData(typeof(IOException))]
    [InlineData(typeof(System.ComponentModel.Win32Exception))]
    public async Task ABridgeThatCannotRunOrTimesOutIsHelixFailedWithTheReason(Type kind)
    {
        AddGame("100", "Plain");
        var bridge = new FakeHelixBridge { Failure = (Exception)Activator.CreateInstance(kind)! };
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed", kind.Name), (job.State, job.Error, job.Detail));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task APythonArchiveThatLeavesItsFolderIsRefusedAndNothingIsUnpacked()
    {
        AddGame("100", "Plain");
        var helix = NewHelix(new FakeHelixBridge());
        SeedHelixArchives(python: new[] { "python.exe", "../evil.dll" });

        var job = await RunInstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "unsafe_archive"), (job.State, job.Error));
        Assert.False(Directory.Exists(helix.PythonFolder));
        Assert.Empty(Directory.GetFileSystemEntries(Path.GetDirectoryName(helix.PythonFolder)!, ".unpack-*"));
        Assert.False(File.Exists(Path.Combine(root, "evil.dll")));
    }

    [Theory]
    [InlineData("HelixSR-3.2.0/../evil.dll")]
    [InlineData("HelixSR-3.2.0/a/../../evil.dll")]
    public async Task AReleaseArchiveThatLeavesItsFolderIsRefusedAndNothingIsKept(string entry)
    {
        AddGame("100", "Plain");
        var helix = NewHelix(new FakeHelixBridge());
        SeedHelixArchives(release: new[] { "HelixSR-3.2.0/setup/helixsr_bridge.py", entry });

        var job = await RunInstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "unsafe_archive"), (job.State, job.Error));
        Assert.False(helix.ReleaseReady);
        Assert.False(File.Exists(Path.Combine(helix.ReleasesFolder, "current")));
        Assert.Empty(Directory.GetFileSystemEntries(helix.ReleasesFolder));
    }

    [Fact]
    public async Task AReleaseWithoutTheBridgeIsNotUnpackedAndAnOldOneStays()
    {
        AddGame("100", "Plain");
        var helix = NewHelix(new FakeHelixBridge());
        SeedHelixRuntime(helix);
        Write(helix.ReleasesFolder, "HelixSR-3.2.0/.panel-complete", new string('b', 64));
        SeedHelixArchives(release: new[] { "HelixSR-3.2.0/LICENSE" });

        var job = await RunInstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "unpack_failed", "bridge missing"), (job.State, job.Error, job.Detail));
        Assert.True(File.Exists(Path.Combine(helix.ReleasesFolder, "HelixSR-3.2.0", "setup", "helixsr_bridge.py")));
        Assert.Empty(Directory.GetFileSystemEntries(helix.ReleasesFolder, ".*"));
    }

    [Fact]
    public async Task ACorruptArchiveIsUnpackFailed()
    {
        AddGame("100", "Plain");
        var helix = NewHelix(new FakeHelixBridge());
        Write(Path.Combine(root, "cache", PythonArchive.Sha256), PythonArchive.FileName, "not a zip");

        var job = await RunInstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "unpack_failed", "InvalidDataException"), (job.State, job.Error, job.Detail));
    }

    [Fact]
    public async Task AnotherToolsUpscalerBesideTheExeIsNeverTouched()
    {
        var game = AddGame("100", "Plain");
        File.WriteAllText(Path.Combine(Target(game), "OptiScaler.ini"), "[Upscalers]");
        var bridge = new FakeHelixBridge();
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal((UpscalerJobStates.Error, "foreign"), (job.State, job.Error));
        Assert.Empty(bridge.Calls);
        Assert.Equal(GameFsr, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
    }

    [Fact]
    public async Task InstallingOverAnOptiScalerInstallTakesItOutFirst()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        Assert.True(File.Exists(Path.Combine(Target(game), "dxgi.dll")));
        var bridge = new FakeHelixBridge();
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.False(File.Exists(Path.Combine(Target(game), "dxgi.dll")));
        Assert.False(File.Exists(Path.Combine(Target(game), GameManifest.Folder, GameManifest.FileName)));
        Assert.Equal(HelixBuild, new UpscalerStateStore(StatePath).Install("100")!.Install.Build);
        Assert.Equal(FakeHelixBridge.Drop, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
    }

    [Fact]
    public async Task SwitchingBackToOptiScalerTakesHelixOutFirst()
    {
        var (game, bridge, helix) = await InstalledHelixAsync();
        var service = Service(prepare: PrepareCache, helix: helix);

        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal((UpscalerJobStates.Done, null), (service.Job!.State, service.Job.Error));
        Assert.Equal("remove", bridge.Calls.Last().Arguments[4]);
        Assert.Equal(GameFsr, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
        Assert.False(File.Exists(Path.Combine(Target(game), "helixsr-install.json")));
        Assert.False(File.Exists(Path.Combine(Target(game), GameManifest.Folder, GameFiles.HelixMarker)));
        var stored = new UpscalerStateStore(StatePath).Install("100")!;
        Assert.Equal(("fsr-3.1", "optiscaler"), (stored.Install.Build, stored.Install.Engine));
        Assert.True(File.Exists(Path.Combine(Target(game), "dxgi.dll")));
    }

    [Fact]
    public async Task AGameWhosePanelStateWasLostIsAdoptedFromTheRecordBesideTheMarker()
    {
        var (game, _, helix) = await InstalledHelixAsync();
        File.Delete(StatePath);
        Assert.True(File.Exists(Path.Combine(Target(game), ".pdc-upscaler", "panel-install.json")));

        var detail = (await Service(helix: helix).HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;

        Assert.Equal(UpscalerGameStates.Installed, detail.Game.State);
        Assert.Equal(("helixsr", HelixBuild), (new UpscalerStateStore(StatePath).Install("100")!.Install.Engine, detail.Install!.Build));
    }

    [Fact]
    public async Task WithoutAnyRecordUninstallStillRemovesHelixSrThroughTheBridge()
    {
        var (game, bridge, helix) = await InstalledHelixAsync();
        File.Delete(StatePath);
        File.Delete(Path.Combine(Target(game), ".pdc-upscaler", "panel-install.json"));

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal(UpscalerJobStates.Done, job.State);
        Assert.Equal("remove", bridge.Calls.Last().Arguments[4]);
        Assert.Equal(GameFsr, File.ReadAllText(Path.Combine(Target(game), FakeHelixBridge.Library)));
        Assert.False(Directory.Exists(Path.Combine(Target(game), ".pdc-upscaler")));
    }

    [Fact]
    public async Task ARunningGameRefusesHelixInstallAndUninstall()
    {
        var (game, _, helix) = await InstalledHelixAsync();
        running.Add(Path.Combine(game, "Binaries", "Win64", "Game.exe"));
        var service = Service(helix: helix);

        var install = await service.HandleAsync(UpscalersRequest.Install("100", HelixBuild, null, null, true), CancellationToken.None);
        var uninstall = await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);

        Assert.Equal(("running", "running"), (install.ErrorCode, uninstall.ErrorCode));
    }

    private static HelixProcessResult InstallThenFail(string[] line, bool removeWorks)
    {
        if (line[4] == "install")
        {
            FakeHelixBridge.Simulate(line);
            return FakeHelixBridge.Fail("died after swapping");
        }

        return removeWorks ? FakeHelixBridge.Simulate(line) : FakeHelixBridge.Fail("remove failed too");
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ABridgeThatFailsAfterSwappingTheDllsPutsTheGamesFileBack(bool bridgeRemoveWorks)
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var bridge = new FakeHelixBridge { Answer = line => InstallThenFail(line, bridgeRemoveWorks) };
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed", "died after swapping"), (job.State, job.Error, job.Detail));
        Assert.Equal(before, Snapshot(game));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task AnInstallTheBridgeAnsweredButPanelCannotVerifyTakesHelixOutOfTheGame()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var bridge = new FakeHelixBridge
        {
            Answer = line =>
            {
                var result = FakeHelixBridge.Simulate(line);
                return line[4] == "install" ? FakeHelixBridge.Ok(game, Path.Combine("..", "elsewhere", "helixsr.log")) : result;
            },
        };
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal((UpscalerJobStates.Error, "install_unverified"), (job.State, job.Error));
        Assert.Equal("remove", bridge.Calls.Last().Arguments[4]);
        Assert.Equal(before, Snapshot(game));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task SwitchingFromOptiScalerToHelixWhoseBridgeFailsDropsTheOptiScalerRecord()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var bridge = new FakeHelixBridge { Answer = _ => FakeHelixBridge.Fail("no write access") };
        SeedHelixArchives();

        var job = await RunInstallAsync(Service(helix: NewHelix(bridge)));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_failed"), (job.State, job.Error));
        Assert.False(File.Exists(Path.Combine(Target(game), "dxgi.dll")));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task RemovingHelixWithNeitherRecordNorBridgeIsRefusedAndKeepsTheMarker()
    {
        var (game, _, helix) = await InstalledHelixAsync();
        File.Delete(Path.Combine(Target(game), "helixsr-install.json"));
        Directory.Delete(helix.ReleasesFolder, true);

        var job = await RunUninstallAsync(Service(helix: helix));

        Assert.Equal((UpscalerJobStates.Error, "helixsr_missing"), (job.State, job.Error));
        Assert.True(File.Exists(Path.Combine(Target(game), GameManifest.Folder, GameFiles.HelixMarker)));
        Assert.NotNull(new UpscalerStateStore(StatePath).Install("100"));
    }
}
