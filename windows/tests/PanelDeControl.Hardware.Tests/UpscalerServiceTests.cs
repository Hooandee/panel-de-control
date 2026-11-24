using System.IO.Pipes;
using System.Net;
using System.Text;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class UpscalerServiceTests : IDisposable
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
        Assert.DoesNotContain(detail.Builds, build => build.Id.EndsWith("-dll", StringComparison.Ordinal));
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
    [InlineData("fsr-4.1.2-dll", null, null, "engine_unsupported")]
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

    private UpscalerService Service(Action<UpscalerStateStore>? seed = null, Action? prepare = null)
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
            () => new GpuFamilyResult("rdna35", "name"),
            () => "rog_ally_x",
            () => 1000,
            (_, _) => { },
            job =>
            {
                deferred.Add(job);
                return Task.CompletedTask;
            });
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

    private static void Write(string folder, string relative, string text)
    {
        var path = Path.Combine(folder, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    private static string Snapshot(string folder) => string.Join("\n", Directory
        .GetFileSystemEntries(folder, "*", SearchOption.AllDirectories)
        .OrderBy(path => path, StringComparer.Ordinal)
        .Select(path => path.Substring(folder.Length) + (File.Exists(path) ? "=" + File.ReadAllText(path) : "/")));

    private sealed class NoNetwork : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
    }
}
