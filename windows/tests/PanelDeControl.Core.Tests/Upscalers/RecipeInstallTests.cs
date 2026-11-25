using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using Xunit;
using PanelDeControl.TestSupport;
using static PanelDeControl.TestSupport.TestTree;

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
        var before = Snapshot(_game);
        var recipe = Resolve("230410");

        var install = await Install(recipe);

        var winmm = Path.Combine(Target, "winmm.dll");
        Assert.Equal("winmm.dll", install.Proxy);
        Assert.Equal("optiscaler", File.ReadAllText(winmm));
        Assert.True(File.GetAttributes(winmm).HasFlag(FileAttributes.ReadOnly));
        Assert.True(GameFiles.ReadManifest(Target)!.ReadOnly);

        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public async Task RecipeFilesGoInAndREFrameworkStartsWithItsMenuClosed()
    {
        Write(Target, ReframeworkConfig.FileName, "Graphics_Fov=90\nREFrameworkConfig_MenuOpen=true\n");
        var before = Snapshot(_game);
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
        Assert.NotEqual(before, Snapshot(_game));
    }

    [Theory]
    [InlineData("1462040", "luma-ff7")]
    [InlineData("1687950", "luma-p5r")]
    public async Task LumaGamesGetTheirPackageAndConfigurationAndLeaveWithoutATrace(string appId, string dependency)
    {
        Unpack(dependency);
        Write(Target, "ReShade.ini", "[Luma]\nSRUserType=0\n[GENERAL]\nValue=mine\n");
        var before = Snapshot(_game);
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
        Assert.Equal(before, Snapshot(_game));
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
        var before = Snapshot(_game);

        var error = await Assert.ThrowsAsync<UpscalerException>(() => Install(Resolve("1462040"), Automatic("1462040")));

        Assert.Equal("recipe_files_invalid", error.Code);
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public void FilesTheUserHasToBringDoNotStopTheInstall()
    {
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        files["games/1462040.json"] = System.Text.Encoding.UTF8.GetBytes(
            System.Text.Encoding.UTF8.GetString(files["games/1462040.json"]).Replace("\"vc-redist-x64\"", "\"puredark-upscaler-base\""));
        var catalog = RecipeCatalog.Load(files);
        var recipe = catalog.Match("1462040", "optiscaler", "windows", "amd64")!;

        var plan = AutomaticRecipe.Plan(catalog, recipe)!;

        Assert.True(AutomaticRecipe.Installable(catalog, recipe));
        Assert.Equal("puredark-upscaler-base", Assert.Single(plan.UserFileDependencies).Id);

    }

    [Fact]
    public async Task AFileTheUserBroughtGoesInWithTheRecipeAndComesOutWithIt()
    {
        Unpack("luma-ff7");
        var (_, recipe, automatic) = RecipeWithUserFile();
        var stored = Path.Combine(_root, "stored", "PDPerfPlugin.dll");
        Write(Path.GetDirectoryName(stored)!, "PDPerfPlugin.dll", "plugin the user downloaded");
        var before = Snapshot(_game);

        var without = await InstallWith(recipe, automatic, userFiles: _ => new Dictionary<string, string>());
        Assert.False(File.Exists(Path.Combine(Target, "PDPerfPlugin.dll")));
        Assert.True(File.Exists(Path.Combine(Target, "ReShade64.dll")));
        Assert.Empty(OptiScalerInstaller.Uninstall(without));
        Assert.Equal(before, Snapshot(_game));

        var with = await InstallWith(recipe, automatic, userFiles: dependency => new Dictionary<string, string> { [dependency.Files.Keys.Single()] = stored });

        Assert.Equal("plugin the user downloaded", File.ReadAllText(Path.Combine(Target, "PDPerfPlugin.dll")));
        Assert.Empty(OptiScalerInstaller.Uninstall(with));
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public async Task AModGoesInBesideTheExeAndTheGameComesBackByteForByteWhenItIsRemoved()
    {
        Write(Target, "ERSS2/ERSS-FG.toml", "[Renderer]\nScalingMode = \"OFF\"\n");
        Write(Target, "mod_loader.dll", "the game's own copy");
        var before = Snapshot(_game);
        var mod = AMod(("dxgi.dll", "mod's own loader"), ("mod_loader.dll", "the mod's version"), ("ERSS2/ERSS-FG.toml", "[Renderer]\nScalingMode = \"MOD\"\n"), ("sub/extra.bin", "extra"));

        var install = await InstallWith(Resolve("1245620"), null, mod: mod);

        Assert.NotEqual("dxgi.dll", install.Proxy);
        Assert.Equal(("mod.zip", "id-1"), (install.Mod!.Value.Key, install.Mod.Value.Value));
        Assert.Equal("mod's own loader", File.ReadAllText(Path.Combine(Target, "dxgi.dll")));
        Assert.Equal("the mod's version", File.ReadAllText(Path.Combine(Target, "mod_loader.dll")));
        Assert.Equal("extra", File.ReadAllText(Path.Combine(Target, "sub", "extra.bin")));
        Assert.Equal("[Renderer]\nScalingMode=\"FSR3U\"\n[FrameGeneration]\nFrameGenMode=1\n", File.ReadAllText(Path.Combine(Target, "ERSS2", "ERSS-FG.toml")));
        var manifest = GameFiles.ReadManifest(Target)!;
        Assert.Contains("dxgi.dll", manifest.Owned);
        Assert.Contains("ERSS2/ERSS-FG.toml", manifest.Owned);
        Assert.Equal(4, manifest.Owned.Count);

        // The game rewrote the mod's own settings while it ran: Panel's files go regardless of what they hold now.
        File.WriteAllText(Path.Combine(Target, "sub", "extra.bin"), "changed by the mod");
        Assert.Empty(OptiScalerInstaller.Uninstall(install));
        Assert.Equal(before, Snapshot(_game));
    }

    [Fact]
    public async Task TheSettingsTheUserLeftInAModAreKeptAcrossAReinstall()
    {
        var mod = AMod(("ERSS2/ERSS-FG.toml", "[Renderer]\nScalingMode = \"MOD\"\n[Other]\nKeep = 1\n"));
        var first = await InstallWith(Resolve("1245620"), null, mod: mod);
        File.WriteAllText(Path.Combine(Target, "ERSS2", "ERSS-FG.toml"), "[Renderer]\nScalingMode = \"FSR3U\"\n[Other]\nKeep = 2\n");

        var second = await InstallWith(Resolve("1245620"), null, previous: first, mod: mod);

        Assert.Equal("[Renderer]\nScalingMode=\"FSR3U\"\n[Other]\nKeep = 2\n[FrameGeneration]\nFrameGenMode=1\n", File.ReadAllText(Path.Combine(Target, "ERSS2", "ERSS-FG.toml")));
        Assert.Empty(OptiScalerInstaller.Uninstall(second));
        Assert.False(Directory.Exists(Path.Combine(Target, "ERSS2")));
    }

    [Fact]
    public async Task AModThatWouldReplaceAPanelFileOrWasAddedForAnotherFolderLeavesTheGameAsItWas()
    {
        var before = Snapshot(_game);

        Assert.Equal("mod_conflict", (await Assert.ThrowsAsync<UpscalerException>(() => InstallWith(null, null, mod: AMod(("OptiScaler.ini", "x"))))).Code);
        Assert.Equal("mod_conflict", (await Assert.ThrowsAsync<UpscalerException>(() => InstallWith(null, null, mod: AMod(("D3D12_Optiscaler/D3D12Core.dll", "x"))))).Code);
        var moved = AMod(("a.dll", "x"));
        moved.Target = "Elsewhere/Win64";
        Assert.Equal("mod_moved", (await Assert.ThrowsAsync<UpscalerException>(() => InstallWith(null, null, mod: moved))).Code);

        Assert.Equal(before, Snapshot(_game));
    }

    private UserModInstall AMod(params (string Destination, string Content)[] files)
    {
        var folder = Path.Combine(_root, "stored-mod");
        foreach (var file in files)
        {
            Write(folder, file.Destination, file.Content);
        }

        return new UserModInstall
        {
            Filename = "mod.zip",
            Id = "id-1",
            Target = "Binaries/Win64",
            GameRoot = _game,
            Sources = files.Select(file => new KeyValuePair<string, string>(file.Destination, Path.Combine(folder, file.Destination.Replace('/', Path.DirectorySeparatorChar)))).ToList(),
        };
    }

    private (RecipeCatalog Catalog, ResolvedRecipe Recipe, AutomaticRecipe Automatic) RecipeWithUserFile()
    {
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        files["games/1462040.json"] = System.Text.Encoding.UTF8.GetBytes(
            System.Text.Encoding.UTF8.GetString(files["games/1462040.json"]).Replace("\"vc-redist-x64\"", "\"puredark-upscaler-base\""));
        var catalog = RecipeCatalog.Load(files);
        var recipe = new RecipeResolver(catalog).Resolve("1462040", "optiscaler", "windows", "x86_64", null, PhysicalFileSystem.Instance, _game)!;
        return (catalog, recipe, AutomaticRecipe.Plan(catalog, catalog.Match("1462040", "optiscaler", "windows", "amd64"))!);
    }

    private Task<InstalledUpscaler> InstallWith(ResolvedRecipe? recipe, AutomaticRecipe? automatic, InstalledUpscaler? previous = null,
        UserModInstall? mod = null, Func<RecipeDependency, IReadOnlyDictionary<string, string>>? userFiles = null) =>
        new OptiScalerInstaller(Catalog, _cache, "rdna35", Path.Combine(_root, "profile")).InstallAsync(Analysis, recipe,
            new OptiScalerInstallRequest { Build = "fsr-3.1" }, previous, _ => previous is not null, null, CancellationToken.None, automatic, mod, userFiles);

    [Theory]
    [InlineData("{ not json")]
    [InlineData("{\"name\": \"Broken\"}")]
    public void ABrokenGameFileIsSkippedAndTheOtherRecipesSurvive(string content)
    {
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        files["games/1462040.json"] = System.Text.Encoding.UTF8.GetBytes(content);
        var skipped = new List<string>();

        var catalog = RecipeCatalog.Load(files, skipped.Add);

        Assert.Contains("games/1462040.json", Assert.Single(skipped));
        Assert.DoesNotContain("1462040", catalog.Games.Keys);
        Assert.Contains("1174180", catalog.Games.Keys);
        Assert.ThrowsAny<Exception>(() => RecipeCatalog.Load(files));
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
    public async Task SettingsUnderDocumentsFollowTheRedirectedDocumentsFolder()
    {
        var documents = Path.Combine(_root, "OneDrive", "Documentos");
        var path = Path.Combine(documents, "Rockstar Games", "Red Dead Redemption 2", "Settings", "system.xml");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "<API>kSettingAPI_Vulkan</API>");
        var recipe = Resolve("1174180");

        var install = await new OptiScalerInstaller(Catalog, _cache, "rdna35", Path.Combine(_root, "profile"), documents).InstallAsync(Analysis, recipe,
            new OptiScalerInstallRequest { Build = "fsr-3.1" }, null, _ => false, null, CancellationToken.None);

        Assert.Equal("<API>kSettingAPI_DX12</API>", File.ReadAllText(path));
        Assert.Equal(path, Assert.Single(install.GameConfig).Path);
        Assert.False(Directory.Exists(Path.Combine(_root, "profile")));
        OptiScalerInstaller.Uninstall(install);
        Assert.Equal("<API>kSettingAPI_Vulkan</API>", File.ReadAllText(path));
    }

    [Fact]
    public async Task SettingsStayChangedWhileTheFilesCouldNotBeRemoved()
    {
        var path = Path.Combine(_root, "profile", "Documents", "Rockstar Games", "Red Dead Redemption 2", "Settings", "system.xml");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "<API>kSettingAPI_Vulkan</API>");
        var install = await Install(Resolve("1174180"));

        IReadOnlyList<string> kept;
        using (new FileStream(Path.Combine(Target, install.Proxy), FileMode.Open, FileAccess.Read, FileShare.None))
        {
            kept = OptiScalerInstaller.Uninstall(install);
        }

        Assert.Contains(install.Proxy, kept);
        Assert.Equal("<API>kSettingAPI_DX12</API>", File.ReadAllText(path));
        Assert.NotNull(GameFiles.ReadManifest(Target));
    }

    [Fact]
    public async Task ADependencyThatPlacesDinput8AlsoGetsREFrameworksMenuClosed()
    {
        Unpack("luma-ff7");
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        files["dependencies.json"] = System.Text.Encoding.UTF8.GetBytes(
            System.Text.Encoding.UTF8.GetString(files["dependencies.json"]).Replace("\"ReShade64.dll\": \"dxgi.dll\"", "\"dinput8.dll\": \"dxgi.dll\""));
        var catalog = RecipeCatalog.Load(files);
        var recipe = new RecipeResolver(catalog).Resolve("1462040", "optiscaler", "windows", "x86_64", null, PhysicalFileSystem.Instance, _game)!;
        var automatic = AutomaticRecipe.Plan(catalog, catalog.Match("1462040", "optiscaler", "windows", "amd64"))!;

        await Install(recipe, automatic);

        Assert.Contains("REFrameworkConfig_MenuOpen=false", File.ReadAllText(Path.Combine(Target, ReframeworkConfig.FileName)));
    }

    [Fact]
    public void AReinstallThatKeptTheEarlierEditStillPutsTheUsersOriginalBack()
    {
        var path = Path.Combine(_root, "profile", "Documents", "settings.xml");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "<API>kSettingAPI_Vulkan</API>");
        var change = new[] { new GameConfigChange("Documents/settings.xml", "API", "kSettingAPI_DX12") };
        var profile = Path.Combine(_root, "profile");
        var first = GameConfigFiles.Apply(profile, change);

        var second = GameConfigFiles.Carry(first, GameConfigFiles.Apply(profile, change));

        Assert.Equal("set", second.Single().State);
        GameConfigFiles.Restore(second);
        Assert.Equal("<API>kSettingAPI_Vulkan</API>", File.ReadAllText(path));
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
    public async Task TheImageReceiptSurvivesTheStateFile()
    {
        var install = await Install(Resolve("1174180"));
        var receipt = new ImageSettingsReceipt
        {
            Target = Path.Combine(Target, GameFiles.IniName),
            Original = { new("Sharpness.Sharpness", "auto") },
            Applied = { new("Sharpness.Sharpness", "0.41") },
        };

        PanelInstallRecord.Write(Target, new StoredUpscaler(install, 1), receipt);

        var read = PanelInstallRecord.ReadReceipt(Target)!;
        Assert.Equal((receipt.Target, "auto", "0.41"), (read.Target, read.Original.Single().Value, read.Applied.Single().Value));
        Assert.NotNull(PanelInstallRecord.Read(Target));
        PanelInstallRecord.Write(Target, new StoredUpscaler(install, 1));
        Assert.Null(PanelInstallRecord.ReadReceipt(Target));
        OptiScalerInstaller.Uninstall(install);
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
}
