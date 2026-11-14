using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Data;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// The neutral catalog and the game recipes must load here exactly as the Linux backend loads them; the expected
/// answers come from tests/test_upscalers_data_parity.py.
/// </summary>
public sealed class DataParityTests
{
    private static readonly string DataDirectory = Path.Combine(AppContext.BaseDirectory, "Data");
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "data_parity.json")))!.AsObject();

    public static IEnumerable<object[]> InvalidCatalogCases() => CaseIds("invalid_catalog");

    public static IEnumerable<object[]> InvalidRecipeCases() => CaseIds("invalid_recipes");

    [Fact]
    public void BuildCatalogLoadsLikeTheLinuxBackend()
    {
        var catalog = BuildCatalog.Parse(File.ReadAllBytes(CatalogPath));
        var expected = Fixture["catalog"]!.AsObject();
        var actual = new JsonObject
        {
            ["archives"] = Map(catalog.Archives),
            ["amd"] = List(catalog.Amd),
            ["every_gpu"] = List(catalog.EveryGpu),
            ["preferred"] = Map(catalog.Preferred),
            ["quality_ratios"] = new JsonObject(catalog.QualityRatios.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value))),
            ["easy_modes"] = Map(catalog.EasyModes),
            ["sharpness"] = new JsonObject(catalog.Sharpness.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value is { } value ? JsonValue.Create(value) : null))),
            ["proxies"] = List(catalog.Proxies),
            ["base_ini"] = Map(catalog.BaseIni),
            ["ffx_loader"] = catalog.FfxLoader,
            ["assets"] = new JsonArray(catalog.Assets.Select(asset => (JsonNode)new JsonObject
            {
                ["id"] = asset.Id, ["filename"] = asset.FileName, ["sha256"] = asset.Sha256, ["size"] = asset.Size,
                ["urls"] = List(asset.Urls), ["archive"] = asset.Archive, ["member"] = asset.Member, ["generation"] = asset.Generation,
            }).ToArray()),
            ["builds"] = new JsonArray(catalog.Builds.Select(build => (JsonNode)new JsonObject
            {
                ["id"] = build.Id, ["family"] = build.Family, ["version"] = build.Version, ["gpus"] = List(build.Gpus),
                ["image"] = build.Image, ["cost"] = build.Cost, ["assets"] = List(build.Assets), ["replace"] = Map(build.Replace),
                ["ini"] = Map(build.Ini), ["injector"] = build.Injector, ["available"] = build.Available, ["archive"] = build.Archive,
                ["channel"] = build.Channel, ["extra_dir"] = build.ExtraDir,
                ["models"] = new JsonArray(build.Models.Select(model => (JsonNode)new JsonArray(model.Id, Map(model.Ini))).ToArray()),
                ["engine"] = build.Engine, ["way"] = build.Way, ["legacy_replace"] = Map(build.LegacyReplace),
            }).ToArray()),
        };
        AssertSame(expected, actual);
    }

    [Fact]
    public void RecipesLoadAndMatchLikeTheLinuxBackend()
    {
        var catalog = RecipeCatalog.Load(RecipeFiles());
        var expected = Fixture["recipes"]!.AsObject();
        Assert.Equal(expected["catalog_version"]!.GetValue<int>(), catalog.CatalogVersion);
        AssertSame(expected["assets"], new JsonObject(catalog.Assets.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, new JsonObject
        {
            ["id"] = pair.Value.Id, ["url"] = pair.Value.Url, ["source_url"] = pair.Value.SourceUrl, ["sha256"] = pair.Value.Sha256,
            ["size"] = pair.Value.Size, ["filename"] = pair.Value.FileName, ["format"] = pair.Value.Format,
        }))));
        AssertSame(expected["dependencies"], new JsonObject(catalog.Dependencies.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, Describe(pair.Value)))));
        AssertSame(expected["games"], new JsonObject(catalog.Games.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, new JsonObject
        {
            ["name"] = pair.Value.Name, ["statuses"] = Map(pair.Value.Statuses),
        }))));

        var matches = new JsonObject();
        foreach (var appId in catalog.Games.Keys.OrderBy(key => key, StringComparer.Ordinal))
        {
            foreach (var engine in Strings(expected["engines"]))
            {
                foreach (var platform in Strings(expected["platforms"]))
                {
                    foreach (var arch in Strings(expected["arches"]))
                    {
                        if (catalog.Match(appId, engine, platform, arch) is { } recipe)
                        {
                            matches[$"{appId}|{engine}|{platform}|{arch}"] = Describe(catalog, recipe);
                        }
                    }
                }
            }
        }
        AssertSame(expected["matches"], matches);
    }

    [Theory]
    [MemberData(nameof(InvalidCatalogCases))]
    public void BrokenCatalogIsRejectedWithTheSameReason(string id)
    {
        var testCase = Case("invalid_catalog", id);
        var bytes = testCase["raw"] is { } raw
            ? Encoding.UTF8.GetBytes(raw.GetValue<string>())
            : Encoding.UTF8.GetBytes(Apply(JsonNode.Parse(File.ReadAllText(CatalogPath)), testCase)!.ToJsonString());
        var error = Assert.Throws<DataFormatException>(() => BuildCatalog.Parse(bytes));
        Assert.Equal(testCase["error"]!.GetValue<string>(), error.Code);
    }

    [Theory]
    [MemberData(nameof(InvalidRecipeCases))]
    public void BrokenRecipesAreRejectedWithTheSameReason(string id)
    {
        var testCase = Case("invalid_recipes", id);
        var files = RecipeFiles().ToDictionary(pair => pair.Key, pair => pair.Value);
        var file = testCase["file"]!.GetValue<string>();
        var current = files.TryGetValue(file, out var bytes) ? JsonNode.Parse(Encoding.UTF8.GetString(bytes)) : null;
        files[file] = Encoding.UTF8.GetBytes(Apply(current, testCase)!.ToJsonString());
        var error = Assert.Throws<DataFormatException>(() => RecipeCatalog.Load(files));
        Assert.Equal(testCase["error"]!.GetValue<string>(), error.Code);
    }

    [Fact]
    public void WindowsFollowsOnlyItsOwnRuntimes()
    {
        var catalog = RecipeCatalog.Load(RecipeFiles());
        var recipe = catalog.Match("1462040", "optiscaler", "windows", "AMD64");
        Assert.NotNull(recipe);
        Assert.Equal(new[] { "vc-redist-x64", "luma-ff7" }, catalog.DependencyOrder(recipe!.Dependencies, "windows").Select(dependency => dependency.Id));
    }

    private static string CatalogPath => Path.Combine(DataDirectory, "Upscalers", "catalog.json");

    private static IReadOnlyDictionary<string, byte[]> RecipeFiles()
    {
        var root = Path.Combine(DataDirectory, "GameRecipes");
        return Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(path => !Path.GetFileName(path).Equals("schema.json", StringComparison.Ordinal))
            .ToDictionary(path => Path.GetRelativePath(root, path).Replace('\\', '/'), File.ReadAllBytes, StringComparer.Ordinal);
    }

    private static JsonNode Describe(RecipeDependency dependency) => new JsonObject
    {
        ["id"] = dependency.Id, ["kind"] = dependency.Kind, ["asset"] = dependency.Asset, ["files"] = Map(dependency.Files),
        ["provider"] = dependency.Provider, ["verb"] = dependency.Verb, ["requires"] = List(dependency.Requires),
        ["name"] = dependency.Name, ["page_url"] = dependency.PageUrl, ["version"] = dependency.Version,
        ["avoid_versions"] = List(dependency.AvoidVersions), ["download_url"] = dependency.DownloadUrl,
    };

    private static JsonNode Describe(RecipeCatalog catalog, GameRecipe recipe) => new JsonObject
    {
        ["appid"] = recipe.AppId, ["name"] = recipe.Name, ["revision"] = recipe.Revision,
        ["conditions"] = new JsonObject(recipe.Conditions.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, List(pair.Value)))),
        ["exe"] = recipe.Exe, ["args"] = List(recipe.Args), ["ini"] = Map(recipe.Ini), ["dependencies"] = List(recipe.Dependencies),
        ["source_urls"] = List(recipe.SourceUrls), ["tested_game_builds"] = List(recipe.TestedGameBuilds), ["tested_at"] = recipe.TestedAt,
        ["configuration"] = new JsonObject(recipe.Configuration.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, Map(pair.Value)))),
        ["recommended_input"] = recipe.RecommendedInput, ["effective_api"] = recipe.EffectiveApi, ["quality_owner"] = recipe.QualityOwner,
        ["recommended_build"] = recipe.RecommendedBuild, ["optiscaler_root_files"] = List(recipe.OptiScalerRootFiles),
        ["reframework_upscaler"] = recipe.ReframeworkUpscaler, ["optiscaler_fg"] = recipe.OptiScalerFrameGeneration,
        ["game_settings"] = new JsonArray(recipe.GameSettings.Select(pair => (JsonNode)new JsonArray(pair.Key, pair.Value)).ToArray()),
        ["platform"] = recipe.Platform, ["status"] = recipe.Status,
        ["ordered_dependencies"] = List(catalog.DependencyOrder(recipe.Dependencies, recipe.Platform).Select(dependency => dependency.Id)),
    };

    private static JsonNode? Apply(JsonNode? document, JsonObject testCase)
    {
        var operation = testCase["op"]!.GetValue<string>();
        if (operation == "create")
        {
            return testCase["value"]!.DeepClone();
        }
        var path = testCase["path"]!.AsArray().ToList();
        var parent = path.Take(path.Count - 1).Aggregate(document!, Step);
        var last = path[^1]!;
        JsonNode? value = operation switch
        {
            "copy" => testCase["from"]!.AsArray().Aggregate(document!, Step).DeepClone(),
            _ => testCase["value"]?.DeepClone(),
        };
        if (parent is JsonArray array)
        {
            array[last.GetValue<int>()] = value;
        }
        else if (operation == "delete")
        {
            parent.AsObject().Remove(last.GetValue<string>());
        }
        else
        {
            parent[last.GetValue<string>()] = value;
        }
        return document;
    }

    private static JsonNode Step(JsonNode node, JsonNode? key) =>
        key!.GetValueKind() == System.Text.Json.JsonValueKind.Number ? node[key.GetValue<int>()]! : node[key.GetValue<string>()]!;

    private static JsonObject Map(IEnumerable<KeyValuePair<string, string>> pairs) =>
        new(pairs.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value)));

    private static JsonArray List(IEnumerable<string> items) => new(items.Select(item => (JsonNode?)item).ToArray());

    private static IEnumerable<string> Strings(JsonNode? node) => node!.AsArray().Select(item => item!.GetValue<string>());

    private static JsonObject Case(string group, string id) =>
        Fixture[group]!.AsArray().Select(item => item!.AsObject()).Single(item => item["id"]!.GetValue<string>() == id);

    private static IEnumerable<object[]> CaseIds(string group) =>
        Fixture[group]!.AsArray().Select(item => new object[] { item!["id"]!.GetValue<string>() });

    private static void AssertSame(JsonNode? expected, JsonNode? actual) =>
        Assert.True(Same(expected, actual), $"expected {expected?.ToJsonString()}\nbut got {actual?.ToJsonString()}");

    /// <summary>Objects compare by key, numbers by value: Python writes 1.0 where .NET writes 1.</summary>
    private static bool Same(JsonNode? expected, JsonNode? actual) => (expected, actual) switch
    {
        (null, null) => true,
        (JsonObject left, JsonObject right) => left.Count == right.Count && left.All(pair => right.ContainsKey(pair.Key) && Same(pair.Value, right[pair.Key])),
        (JsonArray left, JsonArray right) => left.Count == right.Count && left.Zip(right, Same).All(same => same),
        (JsonValue left, JsonValue right) when left.GetValueKind() == System.Text.Json.JsonValueKind.Number
                                             && right.GetValueKind() == System.Text.Json.JsonValueKind.Number =>
            double.Parse(left.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture)
                == double.Parse(right.ToJsonString(), System.Globalization.CultureInfo.InvariantCulture),
        (JsonValue left, JsonValue right) => JsonNode.DeepEquals(left, right),
        _ => false,
    };
}
