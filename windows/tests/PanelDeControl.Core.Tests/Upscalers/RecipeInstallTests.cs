using System.Net;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class RecipeInstallTests : IDisposable
{
    private static readonly string DataDirectory = Path.Combine(AppContext.BaseDirectory, "Data");
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(DataDirectory, "Upscalers", "catalog.json")));
    private static readonly RecipeCatalog Recipes = RecipeCatalog.Load(RecipeFiles());
    private static readonly RecipeResolver Resolver = new(Recipes,
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
        var optiPatcher = Catalog.Asset(Catalog.Archives["optipatcher"])!;
        Write(Path.GetDirectoryName(_cache.FilePath(optiPatcher))!, optiPatcher.FileName, "optipatcher");
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

    [Theory]
    [InlineData("1462040", "luma-ff7")]
    [InlineData("1687950", "luma-p5r")]
    public async Task LumaGamesGetTheirPackageAndConfigurationAndLeaveWithoutATrace(string appId, string dependency)
    {
        Unpack(dependency);
        Write(Target, "ReShade.ini", "[Luma]\nSRUserType=0\n[GENERAL]\nValue=mine\n");
        var before = Snapshot();
        var install = await Install(Resolve(appId), Automatic(appId));

        Assert.Equal("dxgi.dll", File.ReadAllText(Path.Combine(Target, "ReShade64.dll")));
        Assert.Equal("optiscaler", File.ReadAllText(Path.Combine(Target, "dxgi.dll")));
        Assert.True(File.Exists(Path.Combine(Target, "Luma", "d3dcompiler_47.dll")));
        var configured = File.ReadAllText(Path.Combine(Target, "ReShade.ini"));
        Assert.Equal("[Luma]\nSRUserType=2\n[GENERAL]\nValue=mine\n[OVERLAY]\nTutorialProgress=4\n", configured);
        Assert.Contains(Recipes.Dependencies[dependency].Asset!, install.Components.Select(pair => pair.Key));
        Assert.True(GameFiles.ReadManifest(Target)!.HasConfiguration);
        Assert.Empty(Directory.GetDirectories(Path.Combine(_root, "cache"), ".recipe-*"));

        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        Assert.Equal(before, Snapshot());
    }

    [Fact]
    public async Task ConfigurationTheGameRewroteGoesBackKeyByKey()
    {
        Unpack("luma-ff7");
        Write(Target, "ReShade.ini", "[Luma]\nSRUserType=0\n[GENERAL]\nValue=mine\n");
        var install = await Install(Resolve("1462040"), Automatic("1462040"));

        File.AppendAllText(Path.Combine(Target, "ReShade.ini"), "[APP]\nPresets=1\n");
        Assert.Empty(OptiScalerInstaller.Uninstall(install));

        Assert.Equal("[Luma]\nSRUserType=0\n[GENERAL]\nValue=mine\n[OVERLAY]\n[APP]\nPresets=1\n", File.ReadAllText(Path.Combine(Target, "ReShade.ini")));
        Assert.False(File.Exists(Path.Combine(Target, "ReShade64.dll")));
    }

    [Fact]
    public async Task APackageMissingAFileLeavesTheGameAsItWas()
    {
        Unpack("luma-ff7");
        File.Delete(Path.Combine(Unpacked("luma-ff7"), "Luma-Final Fantasy VII Remake.addon"));
        var before = Snapshot();

        var error = await Assert.ThrowsAsync<UpscalerException>(() => Install(Resolve("1462040"), Automatic("1462040")));

        Assert.Equal("recipe_files_invalid", error.Code);
        Assert.Equal(before, Snapshot());
    }

    [Fact]
    public void FilesTheUserHasToBringAreStillRefused()
    {
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        files["games/1462040.json"] = System.Text.Encoding.UTF8.GetBytes(
            System.Text.Encoding.UTF8.GetString(files["games/1462040.json"]).Replace("\"vc-redist-x64\"", "\"puredark-upscaler-base\""));
        var catalog = RecipeCatalog.Load(files);
        var recipe = catalog.Match("1462040", "optiscaler", "windows", "amd64")!;

        Assert.Equal("recipe_unsupported", Assert.Throws<UpscalerException>(() => AutomaticRecipe.Plan(catalog, recipe)).Code);
        Assert.False(AutomaticRecipe.Installable(catalog, recipe));
        Assert.True(AutomaticRecipe.Installable(Recipes, Recipes.Match("1462040", "optiscaler", "windows", "amd64")!));
    }

    [Fact]
    public async Task RedDeadSwitchesToDirectX12AndTheUsersChoiceSurvivesRemoval()
    {
        const string settings = "Documents/Rockstar Games/Red Dead Redemption 2/Settings/system.xml";
        var utf8 = new System.Text.UTF8Encoding(false);
        var path = Path.Combine(_root, "profile", settings.Replace('/', Path.DirectorySeparatorChar));
        var original = "﻿<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n<rage__fwuiSettings>\r\n  <API>kSettingAPI_Vulkan</API>\r\n  <fsr2Index value=\"0\" />\r\n</rage__fwuiSettings>\r\n";
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, utf8.GetBytes(original));

        var install = await Install(Resolve("1174180"));

        Assert.Equal("set", Assert.Single(install.GameConfig).State);
        Assert.Equal(original.Replace("kSettingAPI_Vulkan", "kSettingAPI_DX12"), utf8.GetString(File.ReadAllBytes(path)));
        OptiScalerInstaller.Uninstall(install);
        Assert.Equal(original, utf8.GetString(File.ReadAllBytes(path)));

        install = await Install(Resolve("1174180"));
        var changed = File.ReadAllText(path).Replace("kSettingAPI_DX12", "kSettingAPI_Vulkan").Replace("value=\"0\"", "value=\"1\"");
        File.WriteAllText(path, changed);
        OptiScalerInstaller.Uninstall(install);
        Assert.Equal(changed, File.ReadAllText(path));
    }

    [Fact]
    public async Task RedDeadWithoutItsSettingsYetWritesNothing()
    {
        var install = await Install(Resolve("1174180"));

        Assert.Equal("missing", Assert.Single(install.GameConfig).State);
        Assert.False(Directory.Exists(Path.Combine(_root, "profile")));
        Assert.Empty(OptiScalerInstaller.Uninstall(install));
    }

    [Fact]
    public async Task TheRecordedSettingsSurviveTheStateFile()
    {
        var path = Path.Combine(_root, "profile", "Documents", "Rockstar Games", "Red Dead Redemption 2", "Settings", "system.xml");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "<API>kSettingAPI_Vulkan</API>");
        var install = await Install(Resolve("1174180"));

        PanelInstallRecord.Write(Target, new StoredUpscaler(install, 1));
        var read = PanelInstallRecord.Read(Target)!;

        var record = Assert.Single(read.Install.GameConfig);
        Assert.Equal(("set", "kSettingAPI_Vulkan", path), (record.State, record.Before, record.Path));
        OptiScalerInstaller.Uninstall(read.Install);
        Assert.Equal("<API>kSettingAPI_Vulkan</API>", File.ReadAllText(path));
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

    private Task<InstalledUpscaler> Install(ResolvedRecipe recipe, AutomaticRecipe? automatic = null) =>
        new OptiScalerInstaller(Catalog, _cache, "rdna35", Path.Combine(_root, "profile")).InstallAsync(Analysis, recipe,
            new OptiScalerInstallRequest { Build = "fsr-3.1" }, null, _ => false, null, CancellationToken.None, automatic);

    private static AutomaticRecipe Automatic(string appId) =>
        AutomaticRecipe.Plan(Recipes, Recipes.Match(appId, "optiscaler", "windows", "amd64"))!;

    private string Unpacked(string dependency) =>
        Path.Combine(_root, "cache", Recipes.Assets[Recipes.Dependencies[dependency].Asset!].Sha256, "unpacked");

    private void Unpack(string dependency)
    {
        var folder = Unpacked(dependency);
        Write(folder, ".complete", "x");
        foreach (var member in Recipes.Dependencies[dependency].Files.Values)
        {
            Write(folder, member, member);
        }
    }

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
