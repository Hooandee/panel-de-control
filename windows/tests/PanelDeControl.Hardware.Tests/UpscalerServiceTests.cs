using System.IO.Pipes;
using System.Net;
using System.Text;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;
using PanelDeControl.TestSupport;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests : IDisposable
{
    private static readonly UpscalerData Data = UpscalerData.LoadEmbedded();
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-upscaler-service-" + Guid.NewGuid().ToString("N"));
    private readonly string library;
    private readonly List<string> running = new();
    private readonly List<Func<Task>> deferred = new();

    public UpscalerServiceTests()
    {
        library = Path.Combine(root, "steam");
        Directory.CreateDirectory(Path.Combine(library, "steamapps"));
    }

    public void Dispose() => Directory.Delete(root, true);

    private string StatePath => Path.Combine(root, "state", "state.json");

    [Fact]
    public async Task OverviewSeparatesNoneInstalledAndMissingFromTheManifest()
    {
        AddGame("100", "Plain");
        var installed = AddGame("200", "Patched");
        var gone = AddGame("300", "Lost");
        WriteManifest(Target(installed));
        var service = Service(store =>
        {
            store.SetInstall("200", Install("fsr-3.1", Target(installed)), 10);
            store.SetInstall("300", Install("fsr-3.1", Target(gone)), 10);
        });

        var response = await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None);

        Assert.Equal(UpscalersResponseStatus.Ok, response.Status);
        var games = response.Overview!.Games.ToDictionary(game => game.AppId);
        Assert.Equal(UpscalerGameStates.None, games["100"].State);
        Assert.Equal(UpscalerGameStates.Installed, games["200"].State);
        Assert.Equal("fsr-3.1", games["200"].Build);
        Assert.NotNull(games["200"].Version);
        Assert.Equal(UpscalerGameStates.Missing, games["300"].State);
        Assert.Equal(("rdna35", "name", true), (response.Overview.Gpu, response.Overview.GpuSource, response.Overview.SteamFound));
        Assert.All(games.Values, game => Assert.False(game.Running));
    }

    [Fact]
    public async Task OverviewNamesTheAdapterAndLabelsTheInstalledBuildLikeLinux()
    {
        var installed = AddGame("200", "Patched");
        WriteManifest(Target(installed));
        var service = Service(store => store.SetInstall("200", Install("fsr-3.1", Target(installed)), 10), gpu: new GpuFamilyResult("nvidia", "pci", "NVIDIA GeForce RTX 5090 Laptop GPU"));

        var overview = (await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!;

        Assert.Equal(("nvidia", "NVIDIA GeForce RTX 5090 Laptop GPU"), (overview.Gpu, overview.GpuName));
        Assert.Equal("FSR 3.1.5", overview.Games.Single().Label);
        var detail = (await service.HandleAsync(UpscalersRequest.Game("200"), CancellationToken.None)).Game!;
        Assert.Equal("FSR 3.1.5", detail.Install!.Label);
    }

    [Fact]
    public async Task OnlyGamesAreListedNeverSteamworksRedistributablesOrTools()
    {
        AddGame("100", "Real Game");
        AddGame("228980", "Steamworks Common Redistributables");
        AddGame("1493710", "Proton Experimental");
        AddGame("999", "Not cached");
        WriteAppInfo(("100", "Game"), ("1493710", "Tool"));

        var overview = (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!;

        Assert.Equal(new[] { "100", "999" }, overview.Games.Select(game => game.AppId).OrderBy(id => id, StringComparer.Ordinal).ToArray());
    }

    [Fact]
    public async Task RedistributablesStayOutEvenWhenSteamsCacheIsUnreadable()
    {
        AddGame("100", "Real Game");
        AddGame("228980", "Steamworks Common Redistributables");
        Directory.CreateDirectory(Path.Combine(library, "appcache"));
        File.WriteAllBytes(Path.Combine(library, "appcache", "appinfo.vdf"), new byte[] { 9, 9, 9 });

        var overview = (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!;

        Assert.Equal("100", overview.Games.Single().AppId);
    }

    [Fact]
    public async Task ACoverIsFoundShrunkAndKeptInMemory()
    {
        AddGame("100", "Plain");
        Write(Path.Combine(library, "appcache", "librarycache", "100", "abc123"), "library_600x900.jpg", "portrait");
        Write(Path.Combine(library, "appcache", "librarycache", "100"), "header.jpg", "header");
        var scaled = new List<string>();
        var service = Service(scaleCover: (source, width) =>
        {
            scaled.Add(Encoding.UTF8.GetString(source) + width);
            return new ScaledCover(new byte[] { 1, 2, 3 }, UpscalerCover.Jpeg);
        });

        var first = await service.HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);
        var again = await service.HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);

        Assert.Equal(UpscalersResponseStatus.Ok, first.Status);
        Assert.Equal((UpscalerCover.Jpeg, Convert.ToBase64String(new byte[] { 1, 2, 3 })), (first.Cover!.Mime, first.Cover.Data));
        Assert.Equal(first.Cover.Data, again.Cover!.Data);
        Assert.Equal(new[] { "portrait" + UpscalersWireCodec.MaximumCoverWidth }, scaled);
    }

    [Fact]
    public async Task ACoverFallsBackToTheHeaderAndAGameWithoutOneIsRejected()
    {
        AddGame("100", "Plain");
        AddGame("200", "Bare");
        Write(Path.Combine(library, "appcache", "librarycache"), "100_header.jpg", "legacy header");
        var service = Service(scaleCover: (source, _) => new ScaledCover(source, UpscalerCover.Jpeg));

        var found = await service.HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);
        var none = await service.HandleAsync(UpscalersRequest.Cover("200"), CancellationToken.None);

        Assert.Equal("legacy header", Encoding.UTF8.GetString(Convert.FromBase64String(found.Cover!.Data)));
        Assert.Equal((UpscalersResponseStatus.Rejected, "no_cover"), (none.Status, none.ErrorCode));
    }

    [Fact]
    public async Task AnImageTheScalerCannotReadIsRejected()
    {
        AddGame("100", "Plain");
        Write(Path.Combine(library, "appcache", "librarycache", "100"), "library_600x900.jpg", "not an image");
        var service = Service(scaleCover: (_, _) => null);

        var response = await service.HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, "no_cover"), (response.Status, response.ErrorCode));
    }

    [Fact]
    public void ARealPictureIsShrunkToTheCoverWidthAndKeepsItsFormat()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var scaled = CoverImages.Scale(Png(600, 900), UpscalersWireCodec.MaximumCoverWidth);

        Assert.NotNull(scaled);
        Assert.Equal(UpscalerCover.Png, scaled!.Mime);
        Assert.InRange(scaled.Data.Length, 1, UpscalersWireCodec.MaximumCoverBytes);
        Assert.Equal((200, 300), (ReadInt(scaled.Data, 16), ReadInt(scaled.Data, 20)));
        Assert.Null(CoverImages.Scale(Encoding.UTF8.GetBytes("nope"), 200));
    }

    private static int ReadInt(byte[] data, int offset) => (data[offset] << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3];

    private static byte[] Png(int width, int height)
    {
        var raw = new byte[(width * 3 + 1) * height];
        for (var row = 0; row < height; row++)
        {
            for (var column = 0; column < width; column++)
            {
                raw[row * (width * 3 + 1) + 1 + column * 3] = (byte)(column * 255 / width);
            }
        }

        using var compressed = new MemoryStream();
        using (var zlib = new System.IO.Compression.ZLibStream(compressed, System.IO.Compression.CompressionLevel.Fastest, leaveOpen: true))
        {
            zlib.Write(raw);
        }

        using var output = new MemoryStream();
        output.Write(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A });
        var header = new byte[13];
        BitConverter.GetBytes(IPAddress.HostToNetworkOrder(width)).CopyTo(header, 0);
        BitConverter.GetBytes(IPAddress.HostToNetworkOrder(height)).CopyTo(header, 4);
        header[8] = 8;
        header[9] = 2;
        Chunk(output, "IHDR", header);
        Chunk(output, "IDAT", compressed.ToArray());
        Chunk(output, "IEND", Array.Empty<byte>());
        return output.ToArray();
    }

    private static void Chunk(Stream output, string type, byte[] data)
    {
        output.Write(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(data.Length)));
        var body = Encoding.ASCII.GetBytes(type).Concat(data).ToArray();
        output.Write(body);
        uint crc = 0xFFFFFFFF;
        foreach (var value in body)
        {
            crc ^= value;
            for (var bit = 0; bit < 8; bit++)
            {
                crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
            }
        }

        output.Write(BitConverter.GetBytes(IPAddress.HostToNetworkOrder((int)~crc)));
    }

    private void WriteAppInfo(params (string AppId, string Type)[] apps)
    {
        var entries = new MemoryStream();
        using (var writer = new BinaryWriter(entries, Encoding.UTF8, leaveOpen: true))
        {
            foreach (var (appId, type) in apps)
            {
                var body = new MemoryStream();
                using (var data = new BinaryWriter(body, Encoding.UTF8, leaveOpen: true))
                {
                    data.Write(new byte[60]);
                    data.Write((byte)0);
                    data.Write(Encoding.UTF8.GetBytes("appinfo\0"));
                    data.Write((byte)0);
                    data.Write(Encoding.UTF8.GetBytes("common\0"));
                    data.Write((byte)1);
                    data.Write(Encoding.UTF8.GetBytes("type\0" + type + "\0"));
                    data.Write(new byte[] { 8, 8, 8 });
                }

                writer.Write(uint.Parse(appId));
                writer.Write((uint)body.Length);
                writer.Write(body.ToArray());
            }

            writer.Write(0u);
        }

        var file = new MemoryStream();
        using (var writer = new BinaryWriter(file, Encoding.UTF8, leaveOpen: true))
        {
            writer.Write(0x07564428u);
            writer.Write(1u);
            writer.Write(entries.ToArray());
        }

        Directory.CreateDirectory(Path.Combine(library, "appcache"));
        File.WriteAllBytes(Path.Combine(library, "appcache", "appinfo.vdf"), file.ToArray());
    }

    [Fact]
    public async Task OverviewReportsARunningAndAnUpdatingGame()
    {
        var busy = AddGame("100", "Open");
        AddGame("200", "Updating", flags: 1026);
        running.Add(Path.Combine(busy, "Binaries", "Win64", "Game.exe"));

        var games = (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.ToDictionary(game => game.AppId);

        Assert.True(games["100"].Running);
        Assert.False(games["100"].Updating);
        Assert.True(games["200"].Updating);
    }

    [Fact]
    public async Task AGameWithAnotherToolsUpscalerIsForeign()
    {
        var game = AddGame("100", "Modded");
        File.WriteAllText(Path.Combine(Target(game), "OptiScaler.ini"), "[Upscalers]");

        var overview = (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!;

        Assert.Equal(UpscalerGameStates.Foreign, overview.Games.Single().State);
    }

    [Fact]
    public async Task GameDetailTellsWhatTheFolderHoldsAndWhatCanBeInstalled()
    {
        AddGame("100", "Plain");

        var response = await Service().HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None);

        var detail = response.Game!;
        Assert.Equal("Binaries/Win64/Game.exe", detail.Exe);
        Assert.Contains(detail.Inputs, input => input.Kind == "fsr31");
        Assert.False(detail.AntiCheat);
        Assert.Null(detail.Install);
        Assert.Contains(detail.Builds, build => build.Id == "fsr-3.1");
        Assert.Contains(detail.Builds, build => build.Id.EndsWith("-dll", StringComparison.Ordinal));
        Assert.Contains(detail.Builds, build => build.Id == "hlx-fsr4" && build.Engine == "helixsr");
        Assert.Equal(detail.Preferred, Data.Catalog.Preferred["rdna35"]);
    }

    [Fact]
    public async Task AnUnknownGameIsRejected()
    {
        var response = await Service().HandleAsync(UpscalersRequest.Game("999"), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, "not_installed"), (response.Status, response.ErrorCode));
    }

    [Fact]
    public async Task InstallAndUninstallNeedTheExperimentalFlag()
    {
        AddGame("100", "Plain");
        var service = Service();

        var install = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, false), CancellationToken.None);
        var uninstall = await service.HandleAsync(UpscalersRequest.Uninstall("100", false), CancellationToken.None);
        var overview = await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None);
        var job = await service.HandleAsync(UpscalersRequest.Job(), CancellationToken.None);

        Assert.Equal("experimental_required", install.ErrorCode);
        Assert.Equal("experimental_required", uninstall.ErrorCode);
        Assert.Equal(UpscalersResponseStatus.Ok, overview.Status);
        Assert.Equal(UpscalersResponseStatus.Ok, job.Status);
        Assert.Null(job.Job);
    }

    [Fact]
    public async Task ARunningGameRefusesInstallAndUninstallWithoutStartingAJob()
    {
        var game = AddGame("100", "Open");
        WriteManifest(Target(game));
        var service = Service(store => store.SetInstall("100", Install("fsr-3.1", Target(game)), 1));
        running.Add(Path.Combine(game, "Binaries", "Win64", "Game.exe"));

        var install = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, true), CancellationToken.None);
        var uninstall = await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, "running"), (install.Status, install.ErrorCode));
        Assert.Equal("running", uninstall.ErrorCode);
        Assert.Null(service.Job);
        Assert.True(File.Exists(Path.Combine(Target(game), GameManifest.Folder, GameManifest.FileName)));
    }

    [Theory]
    [InlineData(1026L, "updating")]
    [InlineData(6L, "update_pending")]
    public async Task AnUpdatingGameRefusesInstall(long flags, string code)
    {
        AddGame("100", "Updating", flags);

        var response = await Service().HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, true), CancellationToken.None);

        Assert.Equal(code, response.ErrorCode);
        Assert.Null(Service().Job);
    }

    [Theory]
    [InlineData("nope", null, null, "unknown_build")]
    [InlineData("fsr-3.1", "ultra-fast", null, "invalid_quality")]
    [InlineData("fsr-3.1", null, "no-such-model", "invalid_model")]
    public async Task BadChoicesAreRefusedBeforeAnyJob(string build, string? quality, string? model, string code)
    {
        AddGame("100", "Plain");
        var service = Service();

        var response = await service.HandleAsync(UpscalersRequest.Install("100", build, quality, model, true), CancellationToken.None);

        Assert.Equal((UpscalersResponseStatus.Rejected, code), (response.Status, response.ErrorCode));
        Assert.Null(service.Job);
    }

    [Fact]
    public async Task OnlyOneOperationRunsAtATime()
    {
        AddGame("100", "One");
        AddGame("200", "Two");
        var service = Service();

        var first = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, true), CancellationToken.None);
        var second = await service.HandleAsync(UpscalersRequest.Install("200", "fsr-3.1", null, null, true), CancellationToken.None);

        Assert.Equal("install", first.Job!.Kind);
        Assert.Equal(UpscalerJobStates.Running, first.Job.State);
        Assert.Equal("busy", second.ErrorCode);
        Assert.Equal("100", second.Job!.AppId);
    }

    [Fact]
    public async Task InstallThenUninstallReportsWhatTheManifestSaysAndRestoresTheGame()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var service = Service(prepare: PrepareCache);

        var started = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", "performance", null, true), CancellationToken.None);
        Assert.Equal(UpscalersResponseStatus.Ok, started.Status);
        await RunDeferredAsync();

        var job = (await service.HandleAsync(UpscalersRequest.Job(), CancellationToken.None)).Job!;
        Assert.Equal((UpscalerJobStates.Done, "done", null), (job.State, job.Stage, job.Error));
        var detail = (await service.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;
        Assert.Equal(UpscalerGameStates.Installed, detail.Game.State);
        Assert.Equal(("fsr-3.1", "dxgi.dll", "performance", UpscalerGameStates.Installed),
            (detail.Install!.Build, detail.Install.Proxy, detail.Install.Quality, detail.Install.Status));
        Assert.True(File.Exists(Path.Combine(Target(game), "dxgi.dll")));
        Assert.Contains("\"install\"", File.ReadAllText(StatePath));

        var removed = await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        Assert.Equal(UpscalersResponseStatus.Ok, removed.Status);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal(UpscalerGameStates.None, (await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single().State);
        Assert.Equal(before, Snapshot(game));
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task UninstallTakesOutOnlyTheLaunchArgumentsPanelAdded()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var store = new UpscalerStateStore(StatePath);
        var stored = store.Install("100")!;
        stored.Install.AddedArgs = new[] { "-dx12" };
        store.SetInstall("100", stored.Install, stored.InstalledAt);
        var steam = new FakeLaunchOptions("-dx12 -novid");
        var service = Service(launchOptions: steam);

        await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal("-novid", steam.Value);
    }

    [Fact]
    public async Task WithoutSteamTheLaunchArgumentsStayAndTheUninstallStillFinishes()
    {
        AddGame("100", "Plain");
        await InstallThroughService("100");
        var store = new UpscalerStateStore(StatePath);
        var stored = store.Install("100")!;
        stored.Install.AddedArgs = new[] { "-dx12" };
        store.SetInstall("100", stored.Install, stored.InstalledAt);
        var steam = new FakeLaunchOptions("-dx12") { Available = false };
        var service = Service(launchOptions: steam);

        await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal("-dx12", steam.Value);
        Assert.Contains(new UpscalerStateStore(StatePath).Actions("100"), action => action.Error == "launch_args_kept");
        Assert.Equal(new[] { "-dx12" }, new UpscalerStateStore(StatePath).StrandedArgs("100"));

        // Steam comes back: the next look at a game takes them out.
        steam.Available = true;
        var later = Service(launchOptions: steam);
        await later.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None);
        var deadline = DateTime.UtcNow.AddSeconds(5);
        while (new UpscalerStateStore(StatePath).StrandedArgs("100").Count > 0 && DateTime.UtcNow < deadline)
        {
            await Task.Delay(50);
        }

        Assert.Equal("", steam.Value);
        Assert.Empty(new UpscalerStateStore(StatePath).StrandedArgs("100"));
    }

    [Fact]
    public async Task ARefusedRequestNeverLeavesAJobRunning()
    {
        AddGame("100", "Plain");
        var service = Service(prepare: PrepareCache, gpu: new GpuFamilyResult("nvidia", "name"));

        var refused = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-4.1.2-beta", null, null, true, frameGen: true, frameGenRoute: "anr"), CancellationToken.None);
        var next = await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal("anr_build", refused.ErrorCode);
        Assert.Equal(UpscalersResponseStatus.Ok, next.Status);
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
    }

    [Fact]
    public async Task ADllInstallWhoseStateWasLostIsStillPanelsAndComesOut()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var service = Service(prepare: PrepareDllCache);
        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-4.1.2-dll", null, null, true), CancellationToken.None);
        await RunDeferredAsync();
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        File.Delete(StatePath);

        var fresh = Service();
        var detail = (await fresh.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;
        Assert.Equal("fsr-4.1.2-dll", detail.Install!.Build);
        await fresh.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, fresh.Job!.State);
        Assert.Equal(before, Snapshot(game));
    }

    private void PrepareDllCache()
    {
        var cache = new AssetCache(Path.Combine(root, "cache"), "tar", new NoNetwork(), _ => long.MaxValue, new[] { TimeSpan.Zero });
        foreach (var asset in UpscalerPlanner.BuildAssets(Data.Catalog, Data.Catalog.Build("fsr-4.1.2-dll")!))
        {
            var path = asset.Member is null ? cache.FilePath(asset) : cache.MemberPath(asset);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, asset.Id);
        }
    }

    [Fact]
    public async Task TheGamePageKeepsAHistoryThatTheLogSettles()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var service = Service();
        var first = (await service.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;
        File.WriteAllText(Path.Combine(Target(game), "OptiScaler.log"),
            "[13:19:00.245658] [W] OptiScaler v0.9.4-final (7534ad0) loaded\n" +
            "[13:21:05.132848] [I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\n");

        var second = (await service.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;

        Assert.Equal(("fsr-3.1", "pending"), (first.History!.Single().Build, first.History!.Single().Result));
        Assert.Equal("active", second.Install!.Verdict);
        Assert.Equal("active", second.History!.Single().Result);
        Assert.Equal("active", new UpscalerStateStore(StatePath).History("100").Single().Result);
    }

    private sealed class FakeLaunchOptions : ISteamLaunchOptions
    {
        public FakeLaunchOptions(string value) => Value = value;

        public string Value { get; private set; }

        public bool Available { get; set; } = true;

        public Task<SteamLaunchOptionsResult> ReadAsync(long appId, CancellationToken cancellationToken) =>
            Task.FromResult(Available
                ? new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Read, Value)
                : new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.SteamUnavailable));

        public Task<SteamLaunchOptionsResult> WriteAsync(long appId, string value, bool isNonSteamShortcut, CancellationToken cancellationToken)
        {
            Value = value;
            return Task.FromResult(new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Written, value));
        }
    }

    private async Task InstallThroughService(string appId)
    {
        var service = Service(prepare: PrepareCache);
        await service.HandleAsync(UpscalersRequest.Install(appId, "fsr-3.1", "performance", null, true), CancellationToken.None);
        await RunDeferredAsync();
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
    }

    [Fact]
    public async Task APanelReinstallStillKnowsWhatItInstalledFromTheRecordBesideTheManifest()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var record = Path.Combine(Target(game), ".pdc-upscaler", "panel-install.json");
        Assert.True(File.Exists(record));
        Assert.DoesNotContain("panel-install", File.ReadAllText(Path.Combine(Target(game), ".pdc-upscaler", "manifest.json")));
        File.Delete(StatePath);
        var service = Service();

        var overview = (await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!;

        var row = overview.Games.Single();
        Assert.Equal((UpscalerGameStates.Installed, "fsr-3.1"), (row.State, row.Build));
        Assert.Equal("fsr-3.1", new UpscalerStateStore(StatePath).Install("100")!.Install.Build);
        var detail = (await service.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;
        Assert.Equal(("fsr-3.1", "performance"), (detail.Install!.Build, detail.Install.Quality));

        await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        await RunDeferredAsync();
        Assert.False(File.Exists(record));
        Assert.False(Directory.Exists(Path.Combine(Target(game), ".pdc-upscaler")));
    }

    [Fact]
    public async Task ARecordForAnotherFolderIsIgnoredAndTheInstallIsReportedAsPanelsWithAnUnknownBuild()
    {
        var game = AddGame("100", "Plain");
        await InstallThroughService("100");
        var record = Path.Combine(Target(game), ".pdc-upscaler", "panel-install.json");
        File.WriteAllText(record, File.ReadAllText(record).Replace("Plain", "Elsewhere"));
        File.Delete(StatePath);
        var service = Service();

        var row = (await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single();

        Assert.Equal(UpscalerGameStates.PanelUnknown, row.State);
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task AnOldManifestWithoutARecordIsPanelsAndUninstallRestoresTheFolderFromTheManifestAlone()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        await InstallThroughService("100");
        File.Delete(Path.Combine(Target(game), ".pdc-upscaler", "panel-install.json"));
        File.Delete(StatePath);
        var service = Service();

        var row = (await service.HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single();
        var detail = (await service.HandleAsync(UpscalersRequest.Game("100"), CancellationToken.None)).Game!;

        Assert.Equal(UpscalerGameStates.PanelUnknown, row.State);
        Assert.Equal(("", UpscalerGameStates.Installed), (detail.Install!.Build, detail.Install.Status));
        var removed = await service.HandleAsync(UpscalersRequest.Uninstall("100", true), CancellationToken.None);
        Assert.Equal(UpscalersResponseStatus.Ok, removed.Status);
        await RunDeferredAsync();
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal(before, Snapshot(game));
    }

    [Fact]
    public async Task AnIncompleteManifestIsNeverAdopted()
    {
        var game = AddGame("100", "Plain");
        Write(Target(game), ".pdc-upscaler/manifest.json", "{\"files\": {}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": [], \"incomplete\": true}");

        var row = (await Service().HandleAsync(UpscalersRequest.Overview(), CancellationToken.None)).Overview!.Games.Single();

        Assert.Equal(UpscalerGameStates.None, row.State);
    }

    [Theory]
    [InlineData("library_600x900_spanish.jpg", "header_spanish.jpg", "library_hero.jpg", "library_600x900_spanish.jpg")]
    [InlineData("header.jpg", "library_600x900_spanish.jpg", "library_600x900.jpg", "library_600x900.jpg")]
    [InlineData("header_spanish.jpg", "library_capsule_french.png", "library_hero.jpg", "library_capsule_french.png")]
    [InlineData("header_spanish.jpg", "logo_spanish.png", "library_hero.jpg", "header_spanish.jpg")]
    public async Task ALocalizedCoverIsFoundByPatternAndThePortraitWins(string first, string second, string third, string expected)
    {
        AddGame("100", "Plain");
        var folder = Path.Combine(library, "appcache", "librarycache", "100");
        foreach (var name in new[] { first, second, third })
        {
            Write(folder, name, name);
        }

        var cover = await Service(scaleCover: (source, _) => new ScaledCover(source, UpscalerCover.Jpeg))
            .HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);

        Assert.Equal(expected, Encoding.UTF8.GetString(Convert.FromBase64String(cover.Cover!.Data)));
    }

    [Fact]
    public async Task ALocalizedCoverInsideAHashedSubfolderIsFoundButNeverThroughALink()
    {
        AddGame("100", "Plain");
        var folder = Path.Combine(library, "appcache", "librarycache", "100");
        Write(Path.Combine(folder, "0123abcd"), "library_600x900_latam.jpg", "hashed");
        Write(folder, "library_hero.jpg", "hero");
        var service = Service(scaleCover: (source, _) => new ScaledCover(source, UpscalerCover.Jpeg));

        var found = await service.HandleAsync(UpscalersRequest.Cover("100"), CancellationToken.None);

        Assert.Equal("hashed", Encoding.UTF8.GetString(Convert.FromBase64String(found.Cover!.Data)));
        Assert.Null(CoverFiles.Find(new LinkedFolder(PhysicalFileSystem.Instance, folder), new[] { library }, "100"));
    }

    private sealed class LinkedFolder : IReadOnlyFileSystem
    {
        private readonly IReadOnlyFileSystem inner;
        private readonly string link;

        public LinkedFolder(IReadOnlyFileSystem inner, string link)
        {
            this.inner = inner;
            this.link = link.Replace((char)92, '/');
        }

        public IReadOnlyList<FileSystemEntry> List(string directory) => inner.List(directory);

        public bool IsFile(string path) => inner.IsFile(path);

        public bool IsDirectory(string path) => inner.IsDirectory(path);

        public bool Exists(string path) => inner.Exists(path);

        public bool IsSymbolicLink(string path) => path.Replace((char)92, '/').StartsWith(link, StringComparison.OrdinalIgnoreCase) || inner.IsSymbolicLink(path);

        public long? Length(string path) => inner.Length(path);

        public Stream? OpenRead(string path) => inner.OpenRead(path);
    }

    [Fact]
    public async Task AFailedInstallLeavesAnErrorJobAndAJournalEntry()
    {
        AddGame("100", "Plain");
        var service = Service();

        await service.HandleAsync(UpscalersRequest.Install("100", "fsr-3.1", null, null, true), CancellationToken.None);
        await RunDeferredAsync();

        var job = service.Job!;
        Assert.Equal(UpscalerJobStates.Error, job.State);
        Assert.False(string.IsNullOrEmpty(job.Error));
        var actions = new UpscalerStateStore(StatePath).Actions("100");
        Assert.Equal(new[] { "started", "error" }, actions.Select(action => action.State));
        Assert.Equal(job.Error, actions[1].Error);
        Assert.Null(new UpscalerStateStore(StatePath).Install("100"));
    }

    [Fact]
    public async Task ThePipeAnswersAnOverviewAndRefusesAnInvalidLine()
    {
        AddGame("100", "Plain");
        var pipeName = "pu-" + Guid.NewGuid().ToString("N")[..12];
        var server = new UpscalersPipeServer(pipeName, Service(), name => new NamedPipeServerStream(
            name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));

        var good = await ExchangeAsync(server, pipeName, UpscalersWireCodec.SerializeRequest(UpscalersRequest.Overview()), timeout.Token);
        var bad = await ExchangeAsync(server, pipeName, "{\"operation\":2,\"appid\":\"1\"}", timeout.Token);

        Assert.Equal("100", good.Overview!.Games.Single().AppId);
        Assert.Equal((UpscalersResponseStatus.Rejected, "invalid_upscalers_request"), (bad.Status, bad.ErrorCode));
    }

    [Fact]
    public async Task ASlowRequestDoesNotBlockOtherConnections()
    {
        var pipeName = "pc-" + Guid.NewGuid().ToString("N")[..12];
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var controller = new GatedController(release.Task);
        var server = new UpscalersPipeServer(pipeName, controller, name => new NamedPipeServerStream(
            name, PipeDirection.InOut, 4, PipeTransmissionMode.Byte, PipeOptions.Asynchronous));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var serving = server.RunUntilCancelledAsync(timeout.Token);

        var slow = SendAsync(pipeName, UpscalersWireCodec.SerializeRequest(UpscalersRequest.Overview()), timeout.Token);
        await controller.OverviewStarted.Task.WaitAsync(timeout.Token);
        var fast = await SendAsync(pipeName, UpscalersWireCodec.SerializeRequest(UpscalersRequest.Job()), timeout.Token);

        Assert.Equal(UpscalersResponseStatus.Ok, fast.Status);
        Assert.False(slow.IsCompleted);
        release.SetResult();
        Assert.Equal(UpscalersResponseStatus.Ok, (await slow).Status);
        timeout.Cancel();
        await serving;
    }

    private static async Task<UpscalersResponse> SendAsync(string name, string payload, CancellationToken token)
    {
        await using var client = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous);
        await client.ConnectAsync(token);
        using var reader = new StreamReader(client, new UTF8Encoding(false), false, 256, leaveOpen: true);
        await using var writer = new StreamWriter(client, new UTF8Encoding(false), 256, leaveOpen: true) { AutoFlush = true };
        await writer.WriteLineAsync(payload);
        var line = await reader.ReadLineAsync(token);
        return UpscalersWireCodec.DeserializeResponse(line!);
    }

    private sealed class GatedController : IUpscalersController
    {
        private readonly Task gate;

        public GatedController(Task gate) => this.gate = gate;

        public TaskCompletionSource OverviewStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public async Task<UpscalersResponse> HandleAsync(UpscalersRequest request, CancellationToken cancellationToken)
        {
            if (request.Operation == UpscalersOperation.Overview)
            {
                OverviewStarted.TrySetResult();
                await gate.WaitAsync(cancellationToken);
            }

            return new UpscalersResponse { Status = UpscalersResponseStatus.Ok };
        }
    }

    private static async Task<UpscalersResponse> ExchangeAsync(UpscalersPipeServer server, string name, string payload, CancellationToken token)
    {
        var serving = server.RunOnceAsync(token);
        await using var client = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous);
        await client.ConnectAsync(token);
        using var reader = new StreamReader(client, new UTF8Encoding(false), false, 256, leaveOpen: true);
        await using var writer = new StreamWriter(client, new UTF8Encoding(false), 256, leaveOpen: true) { AutoFlush = true };
        await writer.WriteLineAsync(payload);
        var line = await reader.ReadLineAsync(token);
        await serving;
        return UpscalersWireCodec.DeserializeResponse(line!);
    }

    private UpscalerService Service(Action<UpscalerStateStore>? seed = null, Action? prepare = null, GpuFamilyResult? gpu = null, Func<byte[], int, ScaledCover?>? scaleCover = null,
        ISteamLaunchOptions? launchOptions = null, HelixSr? helix = null, bool noHelix = false)
    {
        var store = new UpscalerStateStore(StatePath);
        seed?.Invoke(store);
        prepare?.Invoke();
        return new UpscalerService(
            Data,
            store,
            new AssetCache(Path.Combine(root, "cache"), "tar", new NoNetwork(), _ => long.MaxValue, new[] { TimeSpan.Zero }),
            PhysicalFileSystem.Instance,
            new SteamGames(PhysicalFileSystem.Instance, () => new[] { library }),
            () => running.ToList(),
            () => gpu ?? new GpuFamilyResult("rdna35", "name"),
            () => "rog_ally_x",
            () => 1000,
            (_, _) => { },
            job =>
            {
                deferred.Add(job);
                return Task.CompletedTask;
            },
            scaleCover,
            launchOptions,
            helix: noHelix ? null : helix ?? NewHelix(new FakeHelixBridge()));
    }

    private async Task RunDeferredAsync()
    {
        var jobs = deferred.ToList();
        deferred.Clear();
        foreach (var job in jobs)
        {
            await job();
        }
    }

    private void PrepareCache()
    {
        var archive = Data.Catalog.Asset("optiscaler-0.9.4")!;
        var release = Path.Combine(root, "cache", archive.Sha256, "unpacked");
        Write(release, ".complete", archive.Sha256);
        Write(release, "OptiScaler.dll", "optiscaler");
        Write(release, "OptiScaler.ini", "[Upscalers]\r\nDx12Upscaler=auto\r\n\r\n[Log]\r\nLogLevel=0\r\n");
        Write(release, "setup_windows.bat", "bat");
        Write(release, "fakenvapi.dll", "fakenvapi");
        Write(release, "D3D12_Optiscaler/D3D12Core.dll", "agility");
        var int8 = Data.Catalog.Asset("amdxcffx64-4.1.1")!;
        Write(Path.Combine(root, "cache"), int8.Sha256 + "/" + int8.FileName, "int8");
    }

    private string AddGame(string appId, string name, long flags = 4)
    {
        var folder = Path.Combine(library, "steamapps", "common", name);
        Write(folder, "Binaries/Win64/Game.exe", "exe");
        Write(folder, "Binaries/Win64/amd_fidelityfx_dx12.dll", "game fsr 3.1");
        File.WriteAllText(
            Path.Combine(library, "steamapps", $"appmanifest_{appId}.acf"),
            $"\"AppState\"\n{{\n\t\"appid\"\t\t\"{appId}\"\n\t\"name\"\t\t\"{name}\"\n\t\"installdir\"\t\t\"{name}\"\n\t\"StateFlags\"\t\t\"{flags}\"\n\t\"buildid\"\t\t\"1\"\n}}\n");
        return folder;
    }

    private static string Target(string game) => Path.Combine(game, "Binaries", "Win64");

    private static InstalledUpscaler Install(string build, string target) => new() { Build = build, Proxy = "dxgi.dll", Target = target };

    private static void WriteManifest(string target)
    {
        Write(target, ".pdc-upscaler/manifest.json", "{\"files\": {}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": []}");
    }
}
