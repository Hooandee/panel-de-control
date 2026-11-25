using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// The plan, the files and the ReShade.ini edits for the Luma games must come out as the Linux backend's
/// <c>auto_recipes</c> answers in recipe_dependencies.json (written by tests/test_upscalers_recipe_dependencies.py).
/// </summary>
public sealed class RecipeDependenciesParityTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "recipe_dependencies.json")))!.AsObject();
    private static readonly RecipeCatalog Catalog = Load();
    private static readonly UTF8Encoding Utf8 = new(false);
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-recipe-deps-" + Guid.NewGuid().ToString("N"));

    public static TheoryData<string> Games() => Names("games");

    public static TheoryData<string> Configured() => Names("configured");

    public static TheoryData<string> Restored() => Names("restored");

    [Theory]
    [MemberData(nameof(Games))]
    public void PlanAssetsAndSourcesMatch(string appId)
    {
        var expected = Fixture["games"]![appId]!.AsObject();
        var recipe = Catalog.Match(appId, "optiscaler", "windows", "amd64")!;
        var automatic = AutomaticRecipe.Plan(Catalog, recipe)!;

        Assert.Equal(
            expected["dependencies"]!.AsArray().Select(item => (item!["id"]!.GetValue<string>(), item["kind"]!.GetValue<string>())),
            Catalog.DependencyOrder(recipe.Dependencies, "windows").Select(dependency => (dependency.Id, dependency.Kind)));
        Assert.Equal(
            expected["assets"]!.AsArray().Select(item => (item!["id"]!.GetValue<string>(), item["filename"]!.GetValue<string>(), item["sha256"]!.GetValue<string>(),
                item["size"]!.GetValue<long>(), string.Join(",", item["urls"]!.AsArray().Select(url => url!.GetValue<string>())))),
            automatic.Assets().Select(asset => (asset.Id, asset.FileName, asset.Sha256, asset.Size, string.Join(",", asset.Urls))));
        Assert.All(automatic.Assets(), asset => Assert.True(asset.Archive));

        var paths = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var pair in expected["members"]!.AsObject())
        {
            var root = Path.Combine(_root, pair.Key);
            foreach (var member in pair.Value!.AsArray())
            {
                var path = Path.Combine(root, member!.GetValue<string>().Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, member.GetValue<string>());
            }
            paths[pair.Key] = root;
        }
        var root0 = Path.GetFullPath(_root) + Path.DirectorySeparatorChar;
        Assert.Equal(
            expected["sources"]!.AsArray().Select(item => (item![0]!.GetValue<string>(), item[1]!.GetValue<string>())),
            automatic.Sources(paths).Select(pair => (pair.Key, string.Join("/", pair.Value.Substring(root0.Length).Split(Path.DirectorySeparatorChar).Skip(1)))));
        Assert.Equal("ReShade.ini", Assert.Single(automatic.Configuration).Key);
        Assert.Equal(
            expected["configuration"]!["ReShade.ini"]!.AsObject().Select(pair => (pair.Key, pair.Value!.GetValue<string>())),
            automatic.Configuration["ReShade.ini"].Select(pair => (pair.Key, pair.Value)));
    }

    [Theory]
    [MemberData(nameof(Configured))]
    public void ConfiguredReShadeIniMatches(string name)
    {
        var expected = Fixture["configured"]![name]!.AsObject();
        var automatic = AutomaticRecipe.Plan(Catalog, Catalog.Match("1462040", "optiscaler", "windows", "amd64"))!;
        var target = Directory.CreateDirectory(Path.Combine(_root, "game")).FullName;
        var staging = Directory.CreateDirectory(Path.Combine(_root, "staging")).FullName;
        if (expected["existing"] is { } existing)
        {
            File.WriteAllBytes(Path.Combine(target, "ReShade.ini"), Utf8.GetBytes(existing.GetValue<string>()));
        }

        if (expected["error"] is { } error)
        {
            Assert.Equal(error.GetValue<string>(), Assert.Throws<UpscalerException>(() => automatic.ConfiguredSources(target, staging)).Code);
            Assert.Empty(Directory.GetFileSystemEntries(staging));
        }
        else
        {
            var result = Assert.Single(automatic.ConfiguredSources(target, staging));
            Assert.Equal("ReShade.ini", result.Key);
            Assert.Equal(expected["text"]!.GetValue<string>(), Utf8.GetString(File.ReadAllBytes(result.Value)));
        }
        Assert.Equal(expected["existing"]?.GetValue<string>(), File.Exists(Path.Combine(target, "ReShade.ini")) ? Utf8.GetString(File.ReadAllBytes(Path.Combine(target, "ReShade.ini"))) : null);
    }

    [Theory]
    [MemberData(nameof(Restored))]
    public void RestoredReShadeIniMatches(string name)
    {
        var expected = Fixture["restored"]![name]!.AsObject();
        Directory.CreateDirectory(_root);
        var path = Path.Combine(_root, "ReShade.ini");
        var backup = Path.Combine(_root, "backup.ini");
        File.WriteAllBytes(path, Utf8.GetBytes(expected["current"]!.GetValue<string>()));
        if (expected["original"] is { } original)
        {
            File.WriteAllBytes(backup, Utf8.GetBytes(original.GetValue<string>()));
        }
        var changes = new Dictionary<string, string>(StringComparer.Ordinal) { ["Luma.SRUserType"] = "2", ["OVERLAY.TutorialProgress"] = "4" };

        if (expected["error"] is { } error)
        {
            Assert.Equal(error.GetValue<string>(), Assert.Throws<UpscalerException>(() => AutomaticRecipe.RestoreConfiguration(path, backup, changes)).Code);
        }
        else
        {
            AutomaticRecipe.RestoreConfiguration(path, backup, changes);
            Assert.Equal(expected["text"]!.GetValue<string>(), Utf8.GetString(File.ReadAllBytes(path)));
        }
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, true);
        }
    }

    private static TheoryData<string> Names(string section)
    {
        var data = new TheoryData<string>();
        foreach (var pair in Fixture[section]!.AsObject())
        {
            data.Add(pair.Key);
        }
        return data;
    }

    private static RecipeCatalog Load()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "Data", "GameRecipes");
        return RecipeCatalog.Load(Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(path => !Path.GetFileName(path).Equals("schema.json", StringComparison.Ordinal))
            .ToDictionary(path => Path.GetRelativePath(root, path).Replace('\\', '/'), File.ReadAllBytes, StringComparer.Ordinal));
    }
}
