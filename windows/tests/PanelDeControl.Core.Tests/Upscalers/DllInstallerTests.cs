using System.Net;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class DllInstallerTests : IDisposable
{
    private const string Provider = DllInstaller.Provider;
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-dll-" + Guid.NewGuid().ToString("N"));
    private readonly string _game;
    private readonly AssetCache _cache;

    public DllInstallerTests()
    {
        _game = Path.Combine(_root, "Game");
        _cache = new AssetCache(Path.Combine(_root, "cache"), "tar", new NoNetwork(), _ => long.MaxValue, new[] { TimeSpan.Zero });
        foreach (var build in new[] { "fsr-4.1.2-lite-dll", "fsr-4.1.2-dll" })
        {
            foreach (var asset in UpscalerPlanner.BuildAssets(Catalog, Catalog.Build(build)!))
            {
                var path = asset.Member is null ? _cache.FilePath(asset) : _cache.MemberPath(asset);
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, asset.Id);
            }
        }
    }

    [Fact]
    public async Task MixedTargetsAreSwappedAndRestoredToTheOriginalBytes()
    {
        var names = new[] { Provider, DllInstaller.Loader, "_storage_/" + DllInstaller.Legacy, "_storage_/" + DllInstaller.Loader, "_storage_/" + Provider };
        foreach (var name in names)
        {
            Write("bin/x64_dx12/" + name, "original:" + name);
        }
        var before = Snapshot();
        var build = Catalog.Build("fsr-4.1.2-lite-dll")!;
        var installer = new DllInstaller(Catalog, _cache);

        var install = await installer.InstallAsync(build.Id, _game, () => Analysis(names.Select(name => "bin/x64_dx12/" + name).ToArray()),
            true, null, false, null, CancellationToken.None);

        Assert.Equal("dll", install.Engine);
        Assert.Equal(build.Replace[Provider], Read("bin/x64_dx12/" + Provider));
        Assert.Equal(build.Replace[Provider], Read("bin/x64_dx12/_storage_/" + Provider));
        Assert.Equal(build.LegacyReplace[DllInstaller.Loader], Read("bin/x64_dx12/_storage_/" + DllInstaller.Legacy));
        Assert.Equal(build.LegacyReplace[DllInstaller.FrameGen], Read("bin/x64_dx12/_storage_/" + DllInstaller.FrameGen));
        Assert.Equal("original:" + DllInstaller.Loader, Read("bin/x64_dx12/" + DllInstaller.Loader));

        Assert.Empty(GameFiles.Remove(install.Target));
        Assert.Equal(before, Snapshot());
    }

    [Fact]
    public async Task ARecipeThatKeepsTheGamesFsr31LibraryLeavesNothingToSwap()
    {
        Write("bin/x64_dx12/" + DllInstaller.Legacy, "ffx 1.0.1");
        var analysis = Analysis(new[] { "bin/x64_dx12/" + DllInstaller.Legacy });

        Assert.Empty(DllInstaller.Targets(analysis, legacySwap: false));
        var error = await Assert.ThrowsAsync<UpscalerException>(() => new DllInstaller(Catalog, _cache)
            .InstallAsync("fsr-4.1.2-dll", _game, () => analysis, false, null, false, null, CancellationToken.None));
        Assert.Equal("dll_no_target", error.Code);
    }

    [Fact]
    public async Task AnOptiScalerInstallInTheRootIsAConflict()
    {
        Write("bin/x64_dx12/" + Provider, "game fsr");
        Write(GameManifest.Folder + "/" + GameManifest.FileName, "{}");

        var error = await Assert.ThrowsAsync<UpscalerException>(() => new DllInstaller(Catalog, _cache)
            .InstallAsync("fsr-4.1.2-dll", _game, () => Analysis(new[] { "bin/x64_dx12/" + Provider }), true, null, false, null, CancellationToken.None));
        Assert.Equal("dll_conflict", error.Code);
    }

    [Fact]
    public async Task AnOptiScalerBuildIsNotADllBuild()
    {
        var error = await Assert.ThrowsAsync<UpscalerException>(() => new DllInstaller(Catalog, _cache)
            .InstallAsync("fsr-3.1", _game, () => Analysis(Array.Empty<string>()), true, null, false, null, CancellationToken.None));
        Assert.Equal("dll_unsupported", error.Code);
    }

    [Fact]
    public async Task AntiCheatNeedsConfirmation()
    {
        Write("bin/x64_dx12/" + Provider, "game fsr");

        var error = await Assert.ThrowsAsync<UpscalerException>(() => new DllInstaller(Catalog, _cache)
            .InstallAsync("fsr-4.1.2-dll", _game, () => Analysis(new[] { "bin/x64_dx12/" + Provider }, antiCheat: true), true, null, false, null, CancellationToken.None));
        Assert.Equal("anti_cheat", error.Code);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, true);
        }
    }

    private GameAnalysis Analysis(IReadOnlyList<string> targets, bool antiCheat = false) => new(
        Array.Empty<ExeCandidate>(), "bin/x64_dx12/Game.exe", new[] { "d3d12" }, false, Path.Combine(_game, "bin", "x64_dx12"),
        Array.Empty<KeyValuePair<string, IReadOnlyList<string>>>(), targets, null, antiCheat, false, null);

    private void Write(string relative, string text)
    {
        var path = Path.Combine(_game, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    private string Read(string relative) => File.ReadAllText(Path.Combine(_game, relative));

    private string Snapshot() => string.Join("\n", Directory
        .GetFileSystemEntries(_game, "*", SearchOption.AllDirectories)
        .OrderBy(path => path, StringComparer.Ordinal)
        .Select(path => path.Substring(_game.Length) + (File.Exists(path) ? "=" + File.ReadAllText(path) : "/")));

    private sealed class NoNetwork : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
    }
}

public sealed class DllTargetSupportTests
{
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));

    [Theory]
    [InlineData("fsr-4.1.2-dll", "bin/amd_fidelityfx_dx12.dll", true)]
    [InlineData("fsr-4.1.2-lite-dll", "bin/amd_fidelityfx_dx12.dll", true)]
    [InlineData("fsr-4.1.2-lite-dll", "bin/amd_fidelityfx_upscaler_dx12.dll|bin/amd_fidelityfx_loader_dx12.dll", true)]
    [InlineData("fsr-4.1.2-lite-dll", "bin/amd_fidelityfx_loader_dx12.dll", false)]
    [InlineData("fsr-4.1.2-dll", "", false)]
    public void OnlyBuildsThatReplaceEveryLibraryTheGameShipsAreOffered(string build, string targets, bool offered)
    {
        var list = targets.Length == 0 ? Array.Empty<string>() : targets.Split('|');
        Assert.Equal(offered, UpscalerPlanner.SupportsDllTargets(Catalog.Build(build)!, list));
    }
}
