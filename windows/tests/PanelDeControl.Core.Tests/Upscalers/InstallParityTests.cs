using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// Installing, removing and recovering must leave every game folder of install_parity.json (written by
/// tests/test_upscalers_install_parity.py) exactly as the Linux backend leaves it, manifest and backups included.
/// </summary>
public sealed class InstallParityTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "install_parity.json")))!.AsObject();
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-install-" + Guid.NewGuid().ToString("N"));

    public static TheoryData<string> Scenarios()
    {
        var data = new TheoryData<string>();
        foreach (var pair in Fixture["scenarios"]!.AsObject())
        {
            data.Add(pair.Key);
        }
        return data;
    }

    [Fact]
    public void ManifestFolderMatches() => Assert.Equal(GameManifest.Folder, Fixture["manifest_dir"]!.GetValue<string>());

    [Theory]
    [MemberData(nameof(Scenarios))]
    public void FolderMatchesAfterEveryStep(string name)
    {
        var scenario = Fixture["scenarios"]![name]!.AsObject();
        var game = Path.Combine(_root, name, "game");
        var cache = Path.Combine(_root, name, "cache");
        Write(game, scenario["game"]!.AsObject());
        Write(cache, Fixture["sources"]!.AsObject());
        var steps = scenario["steps"]!.AsArray();
        var results = scenario["results"]!.AsArray();
        for (var index = 0; index < steps.Count; index++)
        {
            var step = steps[index]!.AsObject();
            var expected = results[index]!.AsObject();
            var label = $"{name} step {index} ({step["op"]})";
            switch (step["op"]!.GetValue<string>())
            {
                case "apply":
                    var sources = step["files"]!.AsObject()
                        .Select(pair => new KeyValuePair<string, string>(pair.Key, Path.Combine(cache, pair.Value!.GetValue<string>())))
                        .ToList();
                    var failAt = step["fail_at"]?.GetValue<int>();
                    var copies = 0;
                    void Copy(string source, string destination)
                    {
                        if (++copies == failAt)
                        {
                            throw new IOException("disk full");
                        }
                        File.Copy(source, destination);
                    }
                    if (expected.ContainsKey("error"))
                    {
                        Assert.Throws<UpscalerException>(() => GameFiles.Apply(game, sources, step["ini"]?.GetValue<string>(), Copy));
                    }
                    else
                    {
                        var manifest = GameFiles.Apply(game, sources, step["ini"]?.GetValue<string>(), Copy);
                        Assert.True(JsonNode.DeepEquals(expected["result"], JsonNode.Parse(manifest.ToJson())), label);
                    }
                    break;
                case "remove":
                    var kept = GameFiles.Remove(game);
                    Assert.Equal(expected["kept"]!.AsArray().Select(item => item!.GetValue<string>()), kept);
                    break;
                case "recover":
                    GameFiles.RecoverOrphan(game, _ => false);
                    break;
                case "write":
                    File.WriteAllText(Path.Combine(game, step["path"]!.GetValue<string>()), step["text"]!.GetValue<string>());
                    break;
                case "delete":
                    File.Delete(Path.Combine(game, step["path"]!.GetValue<string>()));
                    break;
            }
            var tree = Tree(game);
            Assert.True(JsonNode.DeepEquals(expected["tree"], tree), $"{label}\nexpected {expected["tree"]!.ToJsonString()}\nactual   {tree.ToJsonString()}");
        }
    }

    [Fact]
    public void ManifestTextIsWhatPythonWrites()
    {
        var scenario = Fixture["scenarios"]!["install-remove"]!.AsObject();
        var game = Path.Combine(_root, "text", "game");
        var cache = Path.Combine(_root, "text", "cache");
        Write(game, scenario["game"]!.AsObject());
        Write(cache, Fixture["sources"]!.AsObject());
        var step = scenario["steps"]![0]!.AsObject();
        GameFiles.Apply(game, step["files"]!.AsObject()
            .Select(pair => new KeyValuePair<string, string>(pair.Key, Path.Combine(cache, pair.Value!.GetValue<string>()))).ToList(),
            step["ini"]!.GetValue<string>());
        var written = File.ReadAllText(Path.Combine(game, GameManifest.Folder, GameManifest.FileName));
        Assert.StartsWith("{\"files\": {\"dxgi.dll\": \"", written);
        Assert.Contains("\"OptiScaler.ini\": null}, \"backups\": [\"amd_fidelityfx_upscaler_dx12.dll\"], \"dirs\": [\"OptiScaler/D3D12_Optiscaler\"], \"configuration\": {}}", written);
    }

    [Theory]
    [InlineData("{\"files\": {\"../outside.dll\": null}, \"backups\": [], \"dirs\": [], \"configuration\": {}}")]
    [InlineData("{\"files\": {}, \"backups\": [\"..\\\\outside.dll\"], \"dirs\": [], \"configuration\": {}}")]
    [InlineData("{\"files\": {\"/etc/outside.dll\": null}, \"backups\": [], \"dirs\": [], \"configuration\": {}}")]
    [InlineData("{\"files\": {}, \"backups\": [], \"dirs\": [\"a/../..\"], \"configuration\": {}}")]
    public void AnEditedManifestNeverReachesOutsideTheGame(string manifest)
    {
        var game = Path.Combine(_root, "unsafe", "game");
        var outside = Path.Combine(_root, "unsafe", "outside.dll");
        Directory.CreateDirectory(Path.Combine(game, GameManifest.Folder, "backup"));
        File.WriteAllText(outside, "not the game's");
        File.WriteAllText(Path.Combine(game, GameManifest.Folder, GameManifest.FileName), manifest);

        Assert.Equal("unsafe_folder", Assert.Throws<UpscalerException>(() => GameFiles.Remove(game)).Code);
        Assert.True(File.Exists(outside));
        Assert.True(Directory.Exists(Path.Combine(_root, "unsafe")));
    }

    [Theory]
    [MemberData(nameof(IniCases))]
    public void IniMatches(string name)
    {
        var item = Fixture["ini"]![name]!.AsObject();
        var overrides = item["overrides"]!.AsObject().Select(pair => new KeyValuePair<string, string>(pair.Key, pair.Value!.GetValue<string>())).ToList();
        var result = IniText.Apply(item["text"]!.GetValue<string>(), overrides);
        Assert.Equal(item["result"]!.GetValue<string>(), result);
        foreach (var read in item["reads"]!.AsObject())
        {
            Assert.Equal(read.Value?.GetValue<string>(), IniText.Read(result, read.Key));
        }
    }

    [Fact]
    public void PanelIniMatches()
    {
        var catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));
        var panel = Fixture["panel"]!.AsObject();
        var values = panel["values"]!.AsArray();
        var checkedCases = 0;
        foreach (var pair in panel["cases"]!.AsObject())
        {
            var parts = pair.Key.Split('|');
            var inputs = panel["inputs"]![parts[2]]!.AsObject().ToDictionary(
                input => input.Key, input => (IReadOnlyList<string>)input.Value!.AsArray().Select(path => path!.GetValue<string>()).ToList());
            var effective = UpscalerPlanner.ForGame(catalog, catalog.Build(parts[0])!, inputs, parts[1], Array.Empty<string>());
            var generation = catalog.Assets.First(asset => asset.Id == effective.Archive).Generation;
            var plan = UpscalerPlanner.FrameGenPlanFor(parts[1], inputs, null, generation, new[] { "d3d12" }, 2, null);
            var recipe = panel["recipes"]![parts[3]];
            var choice = panel["choices"]![int.Parse(parts[4], System.Globalization.CultureInfo.InvariantCulture)]!.AsObject();
            var result = PanelIni.Compute(catalog, effective,
                recipe?["ini"]!.AsObject().ToDictionary(item => item.Key, item => item.Value!.GetValue<string>()),
                recipe?["optipatcher"]!.GetValue<bool>() ?? false,
                new UpscalerChoice
                {
                    Quality = choice["quality"]?.GetValue<string>(),
                    Sharpness = choice["sharpness"]?.GetValue<string>(),
                    FrameGen = choice["fg"]?.GetValue<string>() == "on",
                    Model = choice["model"]?.GetValue<string>(),
                }, plan);
            var expected = values[pair.Value!.GetValue<int>()]!.AsArray().Select(item => $"{item![0]}={item[1]}");
            Assert.True(expected.SequenceEqual(result.Select(item => $"{item.Key}={item.Value}")), pair.Key);
            checkedCases++;
        }
        Assert.True(checkedCases > 1000);
    }

    public static TheoryData<string> IniCases()
    {
        var data = new TheoryData<string>();
        foreach (var pair in Fixture["ini"]!.AsObject())
        {
            data.Add(pair.Key);
        }
        return data;
    }

    [Theory]
    [InlineData("release-0.9")]
    [InlineData("nightly-10")]
    public void ArchiveSourcesMatch(string name)
    {
        var item = Fixture["archives"]![name]!.AsObject();
        var folder = Path.Combine(_root, "archive-" + name);
        foreach (var file in item["files"]!.AsArray())
        {
            var path = Path.Combine(folder, file!.GetValue<string>());
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "x");
        }
        var sources = OptiScalerRelease.Sources(folder, item["generation"]!.GetValue<int>());
        Assert.Equal(item["sources"]!.AsArray().Select(node => node!.GetValue<string>()), sources.Keys.OrderBy(key => key, StringComparer.Ordinal));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, true);
        }
    }

    private static void Write(string folder, JsonObject files)
    {
        foreach (var pair in files)
        {
            var path = Path.Combine(folder, pair.Key);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, pair.Value!.GetValue<string>());
        }
        Directory.CreateDirectory(folder);
    }

    private static JsonObject Tree(string folder)
    {
        var tree = new SortedDictionary<string, JsonNode?>(StringComparer.Ordinal);
        foreach (var path in Directory.GetFileSystemEntries(folder, "*", SearchOption.AllDirectories))
        {
            var relative = path.Substring(folder.Length + 1).Replace(Path.DirectorySeparatorChar, '/');
            if (Directory.Exists(path))
            {
                if (Directory.GetFileSystemEntries(path).Length == 0)
                {
                    tree[relative + "/"] = null;
                }
                continue;
            }
            var text = File.ReadAllText(path);
            tree[relative] = Path.GetFileName(path) == GameManifest.FileName ? JsonNode.Parse(text) : JsonValue.Create(text);
        }
        var result = new JsonObject();
        foreach (var pair in tree)
        {
            result[pair.Key] = pair.Value;
        }
        return result;
    }
}
