using System.Text.Json;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// A game's recipe must resolve here exactly as <c>recipes.recipe_for</c> and <c>recipes.with_engine</c> resolve it on Linux; the
/// expected answers come from tests/test_upscalers_recipe_resolution.py.
/// </summary>
public sealed class RecipeResolverTests
{
    private const string GameRoot = "C:/Games/Game";
    private static readonly string DataDirectory = Path.Combine(AppContext.BaseDirectory, "Data");
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "recipe_resolution.json")))!.AsObject();
    private static readonly RecipeResolver Resolver = new(RecipeCatalog.Load(RecipeFiles()),
        WikiRecipes.Load(File.ReadAllBytes(Path.Combine(DataDirectory, "Upscalers", "recipes_wiki.json"))));

    public static IEnumerable<object[]> CaseKeys() => Fixture["cases"]!.AsObject().Select(pair => new object[] { pair.Key });

    [Theory]
    [MemberData(nameof(CaseKeys))]
    public void ResolvesLikeTheLinuxBackend(string key)
    {
        var parts = key.Split('|');
        var (platform, appId, engine, marker) = (parts[0], parts[1], parts[2], parts[3] == "re");
        var fileSystem = new InMemoryFileSystem(windows: true);
        fileSystem.AddDirectory(GameRoot);
        if (marker)
        {
            fileSystem.AddFile($"{GameRoot}/{RecipeResolver.ReEngineMarker}", Array.Empty<byte>());
        }

        var resolved = Resolver.Resolve(appId, engine, platform, Fixture["arch"]!.GetValue<string>(), null, fileSystem, GameRoot);

        Assert.True(Same(Fixture["cases"]![key], resolved is null ? null : Describe(resolved)),
            $"expected {Fixture["cases"]![key]?.ToJsonString()}\nbut got {(resolved is null ? "null" : Describe(resolved).ToJsonString())}");
    }

    [Fact]
    public void WindowsKeepsWhatIsNotProtonOnly()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        var warframe = Resolver.Resolve("230410", "optiscaler", "windows", "x86_64", null, fileSystem, GameRoot)!;
        Assert.Equal("winmm.dll", warframe.Proxy);
        Assert.True(warframe.ProtectDlls);
        var cyberpunk = Resolver.Resolve("1091500", "optiscaler", "windows", "x86_64", null, fileSystem, GameRoot)!;
        Assert.Empty(cyberpunk.Args);
        Assert.False(Resolver.Resolve("2322010", "optiscaler", "windows", "x86_64", null, fileSystem, GameRoot)!.LegacyFfxSwap);
    }

    [Fact]
    public void WithoutDataTheGameIsUnknown()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        Assert.Null(new RecipeResolver(null).Resolve("230410", "optiscaler", "windows", "x86_64", null, fileSystem, GameRoot));
        Assert.Null(new RecipeResolver(null, WikiRecipes.Load(new byte[] { 0xff })).Resolve("1938010", "optiscaler", "windows", "x86_64", null, fileSystem, GameRoot));
    }

    private static IReadOnlyDictionary<string, byte[]> RecipeFiles()
    {
        var root = Path.Combine(DataDirectory, "GameRecipes");
        return Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(path => !Path.GetFileName(path).Equals("schema.json", StringComparison.Ordinal))
            .ToDictionary(path => Path.GetRelativePath(root, path).Replace('\\', '/'), File.ReadAllBytes, StringComparer.Ordinal);
    }

    private static JsonNode Describe(ResolvedRecipe recipe) => new JsonObject
    {
        ["appid"] = recipe.AppId, ["exe"] = recipe.Exe, ["args"] = List(recipe.Args), ["files"] = Map(recipe.Files),
        ["native_dlls"] = List(recipe.NativeDlls), ["ini"] = Map(recipe.Ini), ["fg_note"] = recipe.FgNote, ["proxy"] = recipe.Proxy,
        ["needs"] = List(recipe.Needs), ["broken"] = recipe.Broken, ["optipatcher"] = recipe.OptiPatcher, ["menu_key"] = recipe.MenuKey,
        ["status"] = recipe.Status, ["inputs"] = List(recipe.Inputs), ["page"] = recipe.Page, ["linux"] = recipe.Linux,
        ["wiki_settings"] = Map(recipe.WikiSettings), ["wiki_suggestions"] = Map(recipe.WikiSuggestions), ["source"] = recipe.Source,
        ["dependencies"] = List(recipe.Dependencies), ["catalog_revision"] = recipe.CatalogRevision,
        ["recommended_input"] = recipe.RecommendedInput, ["effective_api"] = recipe.EffectiveApi, ["quality_owner"] = recipe.QualityOwner,
        ["recommended_build"] = recipe.RecommendedBuild, ["optiscaler_root_files"] = List(recipe.OptiScalerRootFiles),
        ["reframework_upscaler"] = recipe.ReframeworkUpscaler, ["optiscaler_fg"] = recipe.OptiScalerFrameGeneration,
        ["game_settings"] = Pairs(recipe.GameSettings), ["anr_settings"] = Pairs(recipe.AnrSettings),
        ["mod_launch_exe"] = recipe.ModLaunchExe is { } launch ? new JsonArray(launch.Key, launch.Value) : null,
        ["mod_settings"] = new JsonObject(recipe.ModSettings.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, Map(pair.Value)))),
        ["mod_frame_generation"] = recipe.ModFrameGeneration, ["protect_dlls"] = recipe.ProtectDlls,
        ["game_config"] = new JsonArray(recipe.GameConfig.Select(change => (JsonNode)new JsonArray(change.File, change.Element, change.Value)).ToArray()),
        ["legacy_ffx_swap"] = recipe.LegacyFfxSwap,
    };

    private static JsonArray Pairs(IEnumerable<KeyValuePair<string, string>> pairs) =>
        new(pairs.Select(pair => (JsonNode)new JsonArray(pair.Key, pair.Value)).ToArray());

    private static JsonObject Map(IEnumerable<KeyValuePair<string, string>> pairs) =>
        new(pairs.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value)));

    private static JsonArray List(IEnumerable<string> items) => new(items.Select(item => (JsonNode?)item).ToArray());

    private static bool Same(JsonNode? expected, JsonNode? actual) => (expected, actual) switch
    {
        (null, null) => true,
        (JsonObject left, JsonObject right) => left.Count == right.Count && left.All(pair => right.ContainsKey(pair.Key) && Same(pair.Value, right[pair.Key])),
        (JsonArray left, JsonArray right) => left.Count == right.Count && left.Zip(right, Same).All(same => same),
        (JsonValue left, JsonValue right) when left.GetValueKind() == JsonValueKind.Number && right.GetValueKind() == JsonValueKind.Number =>
            double.Parse(left.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture)
                == double.Parse(right.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture),
        (JsonValue left, JsonValue right) => JsonNode.DeepEquals(left, right),
        _ => false,
    };
}
