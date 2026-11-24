using System.Net;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class RecipeInstallTests : IDisposable
{
    private static readonly string DataDirectory = Path.Combine(AppContext.BaseDirectory, "Data");
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(DataDirectory, "Upscalers", "catalog.json")));
    private static readonly RecipeResolver Resolver = new(RecipeCatalog.Load(RecipeFiles()),
        WikiRecipes.Load(File.ReadAllBytes(Path.Combine(DataDirectory, "Upscalers", "recipes_wiki.json"))));

    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-recipe-" + Guid.NewGuid().ToString("N"));
    private readonly string _game;
    private readonly AssetCache _cache;

    public RecipeInstallTests()
    {
        _game = Path.Combine(_root, "Game");
        Write(_game, "Binaries/Win64/Game.exe", "exe");
        Write(_game, "Binaries/Win64/amd_fidelityfx_dx12.dll", "game fsr 3.1");
        var release = Path.Combine(_root, "cache", Catalog.Asset("optiscaler-0.9.4")!.Sha256, "unpacked");
        Write(release, ".complete", "x");
        Write(release, "OptiScaler.dll", "optiscaler");
        Write(release, "OptiScaler.ini", "[Upscalers]\r\nDx12Upscaler=auto\r\n");
        Write(release, "D3D12_Optiscaler/D3D12Core.dll", "agility");
        _cache = new AssetCache(Path.Combine(_root, "cache"), "tar", new NoNetwork(), _ => long.MaxValue, new[] { TimeSpan.Zero });
        var reframework = Catalog.Asset(ReframeworkConfig.Asset)!;
        Write(Path.GetDirectoryName(_cache.MemberPath(reframework))!, Path.GetFileName(_cache.MemberPath(reframework)), "reframework");
        Write(Path.Combine(_root, "cache"), reframework.Sha256 + "/unpacked/.complete", reframework.Sha256);
    }

    [Fact]
    public async Task WarframeLoadsAsWinmmAndItsLibrariesSurviveTheLauncher()
    {
        var before = Snapshot();
        var recipe = Resolve("230410");

        var install = await Install(recipe);

        var winmm = Path.Combine(Target, "winmm.dll");
        Assert.Equal("winmm.dll", install.Proxy);
        Assert.Equal("optiscaler", File.ReadAllText(winmm));
        Assert.True(File.GetAttributes(winmm).HasFlag(FileAttributes.ReadOnly));
        Assert.True(GameFiles.ReadManifest(Target)!.ReadOnly);

        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        Assert.Equal(before, Snapshot());
    }

    [Fact]
    public async Task RecipeFilesGoInAndREFrameworkStartsWithItsMenuClosed()
    {
        Write(Target, ReframeworkConfig.FileName, "Graphics_Fov=90\nREFrameworkConfig_MenuOpen=true\n");
        var before = Snapshot();
        var recipe = Resolve("2054970");

        var install = await Install(recipe);

        Assert.Equal("reframework", File.ReadAllText(Path.Combine(Target, "dinput8.dll")));
        var seeded = File.ReadAllText(Path.Combine(Target, ReframeworkConfig.FileName));
        Assert.Contains("Graphics_Fov=90", seeded);
        Assert.Contains("REFrameworkConfig_MenuOpen=false", seeded);
        Assert.Contains("REFrameworkConfig_RememberMenuState=true", seeded);

        // REFramework rewrites its config while the game runs: removal keeps that and puts back only Panel's keys.
        File.WriteAllText(Path.Combine(Target, ReframeworkConfig.FileName), seeded + "Graphics_Fov=100\n");
        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        var restored = File.ReadAllText(Path.Combine(Target, ReframeworkConfig.FileName));
        Assert.Contains("REFrameworkConfig_MenuOpen=true", restored);
        Assert.DoesNotContain("REFrameworkConfig_RememberMenuState", restored);
        Assert.False(File.Exists(Path.Combine(Target, "dinput8.dll")));
        Assert.NotEqual(before, Snapshot());
    }

    [Fact]
    public void ReframeworkKeysFollowLinux()
    {
        Assert.Equal("a=1\nTemporalUpscaler_Enabled=true\nTemporalUpscaler_UseNativeResolution=true\n",
            ReframeworkConfig.WithKeys("a=1\nTemporalUpscaler_UpscaleQuality=2\n", ReframeworkConfig.Upscaler("native")
                .Append(new KeyValuePair<string, string?>("TemporalUpscaler_UpscaleQuality", null)).ToList()));
        Assert.Equal("1", ReframeworkConfig.Upscaler(null).Single(pair => pair.Key == "TemporalUpscaler_UpscaleQuality").Value);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            foreach (var file in Directory.GetFiles(_root, "*", SearchOption.AllDirectories))
            {
                File.SetAttributes(file, FileAttributes.Normal);
            }
            Directory.Delete(_root, true);
        }
    }

    private string Target => Path.Combine(_game, "Binaries", "Win64");

    private ResolvedRecipe Resolve(string appId) =>
        Resolver.Resolve(appId, "optiscaler", "windows", "x86_64", null, PhysicalFileSystem.Instance, _game)!;

    private Task<InstalledUpscaler> Install(ResolvedRecipe recipe) =>
        new OptiScalerInstaller(Catalog, _cache, "rdna35").InstallAsync(Analysis, recipe, new OptiScalerInstallRequest { Build = "fsr-3.1" },
            null, _ => false, null, CancellationToken.None);

    private GameAnalysis Analysis() => new(
        Array.Empty<ExeCandidate>(), "Binaries/Win64/Game.exe", new[] { "d3d12", "dxgi" }, false, Target,
        new[] { new KeyValuePair<string, IReadOnlyList<string>>("fsr31", new[] { "Binaries/Win64/amd_fidelityfx_dx12.dll" }) },
        Array.Empty<string>(), null, false, false, null);

    private static IReadOnlyDictionary<string, byte[]> RecipeFiles()
    {
        var root = Path.Combine(DataDirectory, "GameRecipes");
        return Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(path => !Path.GetFileName(path).Equals("schema.json", StringComparison.Ordinal))
            .ToDictionary(path => Path.GetRelativePath(root, path).Replace('\\', '/'), File.ReadAllBytes, StringComparer.Ordinal);
    }

    private static void Write(string root, string relative, string text)
    {
        var path = Path.Combine(root, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

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
