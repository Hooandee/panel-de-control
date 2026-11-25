using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

/// <summary>Runs only when <c>PDC_HELIX_LOCAL</c> names a folder holding the official release and Python archives.</summary>
public sealed class LocalHelixFactAttribute : FactAttribute
{
    public const string Variable = "PDC_HELIX_LOCAL";
    public const string Release = "HelixSR-3.2.0.zip";
    public const string Python = "python.zip";

    public LocalHelixFactAttribute()
    {
        var folder = Folder;
        if (string.IsNullOrEmpty(folder))
        {
            Skip = $"Opt-in: set {Variable} to a folder with {Release} (HelixSR's official release) and {Python} (python.org's embeddable package).";
        }
        else if (!File.Exists(Path.Combine(folder, Release)) || !File.Exists(Path.Combine(folder, Python)))
        {
            Skip = $"{Variable} is set but {Release} or {Python} is missing in {folder}.";
        }
    }

    public static string? Folder => Environment.GetEnvironmentVariable(Variable);
}

public sealed class HelixSrIntegrationTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-helix-real-" + Guid.NewGuid().ToString("N"));

    public HelixSrIntegrationTests() => Directory.CreateDirectory(root);

    public void Dispose() => Directory.Delete(root, true);

    [LocalHelixFact]
    public async Task TheRealBridgeInstallsAndRemovesHlxFsr4InAFakeGameWithoutTouchingAnythingElse()
    {
        var data = UpscalerData.LoadEmbedded();
        var build = data.Catalog.Build("hlx-fsr4")!;
        var release = data.Catalog.Asset(build.Archive)!;
        var python = data.Catalog.Asset(build.AssetsFor("windows").Single())!;
        var archives = LocalHelixFactAttribute.Folder!;
        Assert.Equal(release.Sha256, AssetCache.Sha256(Path.Combine(archives, LocalHelixFactAttribute.Release)));
        Assert.Equal(python.Sha256, AssetCache.Sha256(Path.Combine(archives, LocalHelixFactAttribute.Python)));
        var helix = HelixSr.ForCatalog(data.Catalog, Path.Combine(root, "upscalers"));

        helix.UnpackPython(Path.Combine(archives, LocalHelixFactAttribute.Python), python.Sha256);
        helix.UnpackRelease(Path.Combine(archives, LocalHelixFactAttribute.Release), release.Sha256);

        Assert.True(helix.Ready);
        Assert.Equal(release.Sha256, helix.Digest);
        var game = Directory.CreateDirectory(Path.Combine(root, "Fake Game")).FullName;
        var binaries = Directory.CreateDirectory(Path.Combine(game, "Binaries", "Win64")).FullName;
        File.WriteAllText(Path.Combine(binaries, "Game.exe"), "MZ fake executable");
        File.WriteAllText(Path.Combine(binaries, "amd_fidelityfx_dx12.dll"), "the game's own FSR 3.1");
        var before = Directory.GetFileSystemEntries(game, "*", SearchOption.AllDirectories).Length;

        var installed = await helix.InstallAsync(game, CancellationToken.None);

        Assert.Equal(binaries, installed.ExeFolder);
        Assert.True(File.Exists(Path.Combine(binaries, "helixsr-install.json")));
        Assert.True(new FileInfo(Path.Combine(binaries, "amd_fidelityfx_dx12.dll")).Length > 1_000_000);
        Assert.Equal("the game's own FSR 3.1", File.ReadAllText(Path.Combine(binaries, "amd_fidelityfx_dx12.original.dll")));
        Assert.True(HelixRestore.IsHelixFile(Path.Combine(binaries, "amd_fidelityfx_dx12.dll")));

        await helix.RemoveAsync(game, CancellationToken.None);

        Assert.Equal("the game's own FSR 3.1", File.ReadAllText(Path.Combine(binaries, "amd_fidelityfx_dx12.dll")));
        Assert.False(File.Exists(Path.Combine(binaries, "helixsr-install.json")));
        Assert.Equal(before, Directory.GetFileSystemEntries(game, "*", SearchOption.AllDirectories).Length);

        var again = await Assert.ThrowsAsync<UpscalerException>(() => helix.RemoveAsync(game, CancellationToken.None));
        Assert.Equal("helixsr_failed", again.Code);
        Assert.True(HelixBridge.NotInstalled(again.Detail), again.Detail);
    }
}
