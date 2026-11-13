using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>The same cases tests/test_upscalers_shared_fixtures.py runs against the Linux backend.</summary>
public sealed class SharedFixtureTests
{
    private static readonly string FixtureDirectory = Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers");

    public static IEnumerable<object[]> PeCases() => CaseIds("pe_images.json");

    public static IEnumerable<object[]> GameFolderCases() => CaseIds("game_folders.json");

    public static IEnumerable<object[]> SteamCases() => CaseIds("steam_library.json");

    [Theory]
    [MemberData(nameof(PeCases))]
    public void PeImageMatchesTheLinuxBackend(string id)
    {
        var document = Load("pe_images.json");
        var fixture = Case(document, id);
        var image = ImageBytes(document, fixture["input"]!["image"]!.GetValue<string>());
        var fileSystem = new InMemoryFileSystem();
        fileSystem.AddFile("/image.exe", image);
        JsonNode? actual = fixture["operation"]!.GetValue<string>() switch
        {
            "imported_dlls" => ImportedDlls(image),
            "graphics_apis" => Strings(PeImage.GraphicsApis(new MemoryStream(image))),
            "version_strings" => new JsonObject(PeImage.VersionStrings(new MemoryStream(image))
                .Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value))),
            "embedded_upscalers" => Strings(GameFolder.EmbeddedUpscalers(fileSystem, "/image.exe").OrderBy(kind => kind, StringComparer.Ordinal)),
            "streamline_major" => GameFolder.StreamlineMajor(fileSystem, "/image.exe") is { } major ? JsonValue.Create(major) : null,
            var operation => throw new InvalidOperationException(operation),
        };
        AssertSame(fixture["expected"], actual);
    }

    [Theory]
    [MemberData(nameof(GameFolderCases))]
    public void GameFolderMatchesTheLinuxBackend(string id)
    {
        var document = Load("game_folders.json");
        var fixture = Case(document, id);
        var input = fixture["input"]!;
        var root = $"/fixture/{id}/game";
        var fileSystem = new InMemoryFileSystem();
        Materialize(fileSystem, root, document["trees"]![input["tree"]!.GetValue<string>()]!, Load("pe_images.json"));
        JsonNode? actual = fixture["operation"]!.GetValue<string>() switch
        {
            "analyze" => Describe(GameFolder.Analyze(fileSystem, root, input["chosen_exe"]?.GetValue<string>(), input["recipe_exe"]?.GetValue<string>()), root),
            "shipped_upscalers" => Strings(GameFolder.ShippedUpscalers(fileSystem, root)),
            "graphics_apis" => Strings(GameFolder.GraphicsApis(fileSystem, root + "/" + input["exe"]!.GetValue<string>())),
            var operation => throw new InvalidOperationException(operation),
        };
        AssertSame(fixture["expected"], actual);
    }

    [Theory]
    [MemberData(nameof(SteamCases))]
    public void SteamLibraryMatchesTheLinuxBackend(string id)
    {
        var fixture = Case(Load("steam_library.json"), id);
        var input = fixture["input"]!;
        var root = $"/fixture/{id}";
        var steamRoot = root + "/home/.local/share/Steam";
        JsonNode? actual;
        switch (fixture["operation"]!.GetValue<string>())
        {
            case "update_state":
                actual = SteamLibrary.UpdateState(input["flags"]!.GetValue<long>()) is { } state ? Wire(state) : null;
                break;
            case "parse_vdf":
                var bytes = input["base64"] is { } encoded
                    ? Convert.FromBase64String(encoded.GetValue<string>())
                    : Encoding.UTF8.GetBytes(input["text"]!.GetValue<string>());
                try
                {
                    actual = new JsonObject { ["value"] = Describe(ValveTextVdf.Parse(bytes)) };
                }
                catch (VdfFormatException error)
                {
                    actual = new JsonObject { ["error"] = error.Code };
                }

                break;
            default:
                var fileSystem = new InMemoryFileSystem();
                Materialize(fileSystem, root, input, document: null);
                var libraries = SteamLibrary.LibraryPaths(fileSystem, new[] { steamRoot });
                if (fixture["operation"]!.GetValue<string>() == "library_paths")
                {
                    actual = Strings(libraries.Select(path => Relative(root, path)));
                    break;
                }

                var app = SteamLibrary.FindInstalled(fileSystem, libraries, input["appid"]!.GetValue<string>());
                actual = app is null ? null : new JsonObject
                {
                    ["appid"] = app.AppId,
                    ["name"] = app.Name,
                    ["root"] = Relative(root, app.Root),
                    ["state_flags"] = app.StateFlags,
                    ["build_id"] = app.BuildId,
                    ["update_state"] = app.UpdateState is { } update ? Wire(update) : null,
                };
                break;
        }

        AssertSame(fixture["expected"], actual);
    }

    private static JsonNode ImportedDlls(byte[] image)
    {
        try
        {
            return new JsonObject { ["dlls"] = Strings(PeImage.ImportedDlls(new MemoryStream(image)).OrderBy(name => name, StringComparer.Ordinal)) };
        }
        catch (InvalidDataException)
        {
            return new JsonObject { ["error"] = true };
        }
    }

    private static JsonObject Describe(GameAnalysis analysis, string root) => new()
    {
        ["candidates"] = new JsonArray(analysis.Candidates.Select(candidate => (JsonNode)new JsonObject
        {
            ["exe"] = candidate.Exe,
            ["apis"] = Strings(candidate.Apis),
            ["size"] = candidate.Size,
            ["score"] = candidate.Score,
        }).ToArray()),
        ["exe"] = analysis.Exe,
        ["apis"] = Strings(analysis.Apis),
        ["manual"] = analysis.Manual,
        ["target"] = analysis.Target is null ? null : Relative(root, analysis.Target),
        ["inputs"] = new JsonObject(analysis.Inputs.Select(input => new KeyValuePair<string, JsonNode?>(input.Key, Strings(input.Value)))),
        ["dll_targets"] = Strings(analysis.DllTargets),
        ["streamline"] = analysis.Streamline,
        ["anti_cheat"] = analysis.AntiCheat,
        ["foreign"] = analysis.Foreign,
        ["foreign_identity"] = analysis.ForeignIdentity is not { } identity ? null : new JsonObject
        {
            ["engine"] = identity.Engine,
            ["variant"] = identity.Variant,
            ["evidence"] = Strings(identity.Evidence),
            ["manifest_error"] = identity.ManifestError,
        },
    };

    private static JsonObject Describe(VdfObject value) => new(value.Entries.Select(entry => new KeyValuePair<string, JsonNode?>(
        entry.Key,
        entry.Value is VdfObject nested ? Describe(nested) : JsonValue.Create((string)entry.Value))));

    private static string Wire(SteamUpdateState state) => state == SteamUpdateState.Running ? "running" : "pending";

    private static void Materialize(InMemoryFileSystem fileSystem, string root, JsonNode tree, JsonObject? document)
    {
        fileSystem.AddDirectory(root);
        foreach (var directory in tree["dirs"]?.AsArray() ?? new JsonArray())
        {
            fileSystem.AddDirectory(root + "/" + directory!.GetValue<string>());
        }

        foreach (var (relative, entry) in tree["files"]?.AsObject() ?? new JsonObject())
        {
            var content = entry!["image"] is { } image
                ? ImageBytes(document!, image.GetValue<string>())
                : entry["text"] is { } text
                    ? Encoding.UTF8.GetBytes(text.GetValue<string>().Replace("{root}", root))
                    : entry["base64"] is { } encoded ? Convert.FromBase64String(encoded.GetValue<string>()) : "x"u8.ToArray();
            fileSystem.AddFile(root + "/" + relative, content, entry["size"]?.GetValue<long>());
        }

        foreach (var (relative, target) in tree["symlinks"]?.AsObject() ?? new JsonObject())
        {
            fileSystem.AddLink(root + "/" + relative, root + "/" + target!.GetValue<string>());
        }
    }

    private static string Relative(string root, string path) =>
        path == root ? "." : path.StartsWith(root + "/", StringComparison.Ordinal) ? path.Substring(root.Length + 1) : path;

    private static JsonArray Strings(IEnumerable<string> values) => new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());

    private static void AssertSame(JsonNode? expected, JsonNode? actual)
    {
        Assert.True(JsonNode.DeepEquals(expected, actual), $"expected {expected?.ToJsonString()} but got {actual?.ToJsonString()}");
    }

    private static byte[] ImageBytes(JsonObject document, string id) =>
        Convert.FromBase64String(document["images"]![id]!["base64"]!.GetValue<string>());

    private static JsonObject Load(string name) =>
        JsonNode.Parse(File.ReadAllText(Path.Combine(FixtureDirectory, name)))!.AsObject();

    private static JsonObject Case(JsonObject document, string id) =>
        document["cases"]!.AsArray().Select(item => item!.AsObject()).Single(item => item["id"]!.GetValue<string>() == id);

    private static IEnumerable<object[]> CaseIds(string name) =>
        Load(name)["cases"]!.AsArray().Select(item => new object[] { item!["id"]!.GetValue<string>() });
}
