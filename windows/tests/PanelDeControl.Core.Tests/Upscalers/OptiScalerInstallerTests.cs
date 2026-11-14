using System.Net;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class OptiScalerInstallerTests : IDisposable
{
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-installer-" + Guid.NewGuid().ToString("N"));
    private readonly string _game;
    private readonly AssetCache _cache;

    public OptiScalerInstallerTests()
    {
        _game = Path.Combine(_root, "Game");
        Write(_game, "Binaries/Win64/Game.exe", "exe");
        Write(_game, "Binaries/Win64/amd_fidelityfx_dx12.dll", "game fsr 3.1");
        Write(_game, "Binaries/Win64/dxgi.dll", "game's own dxgi");
        var release = Unpacked(Catalog.Asset("optiscaler-0.9.4")!);
        Write(release, "OptiScaler.dll", "optiscaler");
        Write(release, "OptiScaler.ini", "[Upscalers]\r\nDx12Upscaler=auto\r\n\r\n[Log]\r\nLogLevel=0\r\n");
        Write(release, "setup_windows.bat", "bat");
        Write(release, "fakenvapi.dll", "fakenvapi");
        Write(release, "D3D12_Optiscaler/D3D12Core.dll", "agility");
        Write(_root, "cache/" + Catalog.Asset("amdxcffx64-4.1.1")!.Sha256 + "/" + Catalog.Asset("amdxcffx64-4.1.1")!.FileName, "int8");
        _cache = new AssetCache(Path.Combine(_root, "cache"), "/usr/bin/tar", new NoNetwork(), _ => long.MaxValue, new[] { TimeSpan.Zero });
    }

    [Fact]
    public async Task InstallsTheReleaseAndRemovesItExactly()
    {
        var before = Snapshot(_game);
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");

        var install = await installer.InstallAsync(Analysis, null, new OptiScalerInstallRequest
        {
            Build = "fsr-3.1",
            Choice = new UpscalerChoice { Quality = "performance", Sharpness = "soft" },
        }, null, _ => false, null, CancellationToken.None);

        var exeFolder = Path.Combine(_game, "Binaries", "Win64");
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(exeFolder, "dxgi.dll")));
        Assert.Equal("agility", File.ReadAllText(Path.Combine(exeFolder, "D3D12_Optiscaler", "D3D12Core.dll")));
        Assert.False(File.Exists(Path.Combine(exeFolder, "setup_windows.bat")));
        var ini = File.ReadAllText(Path.Combine(exeFolder, "OptiScaler.ini"));
        Assert.Equal("fsr31", IniText.Read(ini, "Upscalers.Dx12Upscaler"));
        Assert.Equal("2.00", IniText.Read(ini, "QualityOverrides.QualityRatioPerformance"));
        Assert.Equal("0.30", IniText.Read(ini, "Sharpness.Sharpness"));
        Assert.Contains("\r\n", ini);
        Assert.Equal("dxgi.dll", install.Proxy);
        Assert.Equal(exeFolder, install.Target);
        Assert.Contains("FrameGen.Enabled", install.Managed);

        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public async Task ANewVersionReplacesTheOldOneAndStillRestoresTheGame()
    {
        var before = Snapshot(_game);
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");
        var first = await installer.InstallAsync(Analysis, null, new OptiScalerInstallRequest { Build = "fsr-3.1" }, null, _ => false, null, CancellationToken.None);

        var second = await installer.InstallAsync(Analysis, null, new OptiScalerInstallRequest { Build = "fsr-4.1.1", Proxy = "winmm.dll" },
            first, _ => false, null, CancellationToken.None);

        var exeFolder = Path.Combine(_game, "Binaries", "Win64");
        Assert.Equal("game's own dxgi", File.ReadAllText(Path.Combine(exeFolder, "dxgi.dll")));
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(exeFolder, "winmm.dll")));
        Assert.Equal("int8", File.ReadAllText(Path.Combine(exeFolder, "amdxcffx64.dll")));
        OptiScalerInstaller.Uninstall(second);
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public async Task AFailedDownloadLeavesTheGameAndThePreviousInstallAlone()
    {
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");
        var first = await installer.InstallAsync(Analysis, null, new OptiScalerInstallRequest { Build = "fsr-3.1" }, null, _ => false, null, CancellationToken.None);
        var installed = Snapshot(_game);

        var error = await Assert.ThrowsAsync<AssetException>(() => installer.InstallAsync(Analysis, null,
            new OptiScalerInstallRequest { Build = "fsr-4.0.2c" }, first, path => path == first.Target, null, CancellationToken.None));

        Assert.Equal("download_failed", error.Code);
        Assert.Equal(installed, Snapshot(_game));
    }

    [Theory]
    [InlineData("fsr-4.1.2-dll", "engine_unsupported")]
    [InlineData("nope", "unknown_build")]
    public async Task OnlyOptiScalerBuildsInstallHere(string build, string code)
    {
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");
        var error = await Assert.ThrowsAsync<UpscalerException>(() => installer.InstallAsync(Analysis, null,
            new OptiScalerInstallRequest { Build = build }, null, _ => false, null, CancellationToken.None));
        Assert.Equal(code, error.Code);
    }

    [Fact]
    public async Task AnUnknownProxyIsRefused()
    {
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");
        var error = await Assert.ThrowsAsync<UpscalerException>(() => installer.InstallAsync(Analysis, null,
            new OptiScalerInstallRequest { Build = "fsr-3.1", Proxy = "kernel32.dll" }, null, _ => false, null, CancellationToken.None));
        Assert.Equal("invalid_proxy", error.Code);
    }

    [Fact]
    public async Task AntiCheatNeedsConfirmation()
    {
        var installer = new OptiScalerInstaller(Catalog, _cache, "rdna35");
        var error = await Assert.ThrowsAsync<UpscalerException>(() => installer.InstallAsync(() => Analyzed(antiCheat: true), null,
            new OptiScalerInstallRequest { Build = "fsr-3.1" }, null, _ => false, null, CancellationToken.None));
        Assert.Equal("anti_cheat", error.Code);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, true);
        }
    }

    private GameAnalysis Analysis() => Analyzed();

    private GameAnalysis Analyzed(bool antiCheat = false) => new(
        Array.Empty<ExeCandidate>(), "Binaries/Win64/Game.exe", new[] { "d3d12", "dxgi" }, false, Path.Combine(_game, "Binaries", "Win64"),
        new[] { new KeyValuePair<string, IReadOnlyList<string>>("fsr31", new[] { "Binaries/Win64/amd_fidelityfx_dx12.dll" }) },
        Array.Empty<string>(), null, antiCheat, false, null);

    private string Unpacked(UpscalerAsset asset)
    {
        var folder = Path.Combine(_root, "cache", asset.Sha256, "unpacked");
        Write(folder, ".complete", asset.Sha256);
        return folder;
    }

    private static void Write(string root, string relative, string text)
    {
        var path = Path.Combine(root, relative);
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
