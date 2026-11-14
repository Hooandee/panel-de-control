using System.Globalization;
using System.Numerics;
using System.Text.RegularExpressions;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

public sealed class RecipeAsset
{
    internal RecipeAsset(string id, string url, string sourceUrl, string sha256, long size, string fileName, string format)
    {
        Id = id;
        Url = url;
        SourceUrl = sourceUrl;
        Sha256 = sha256;
        Size = size;
        FileName = fileName;
        Format = format;
    }

    public string Id { get; }

    public string Url { get; }

    public string SourceUrl { get; }

    public string Sha256 { get; }

    public long Size { get; }

    public string FileName { get; }

    public string Format { get; }
}

public sealed class RecipeDependency
{
    internal RecipeDependency()
    {
    }

    public string Id { get; internal set; } = "";

    /// <summary><c>game_files</c>, <c>proton_dependency</c>, <c>windows_redist</c> or <c>user_files</c>.</summary>
    public string Kind { get; internal set; } = "";

    public string? Asset { get; internal set; }

    public IReadOnlyDictionary<string, string> Files { get; internal set; } = new Dictionary<string, string>();

    public string? Provider { get; internal set; }

    /// <summary>The winetricks verb, or the Windows runtime component.</summary>
    public string? Verb { get; internal set; }

    public IReadOnlyList<string> Requires { get; internal set; } = Array.Empty<string>();

    public string? Name { get; internal set; }

    public string? PageUrl { get; internal set; }

    /// <summary>The user file's version, or the minimum runtime version.</summary>
    public string? Version { get; internal set; }

    public IReadOnlyList<string> AvoidVersions { get; internal set; } = Array.Empty<string>();

    public string? DownloadUrl { get; internal set; }
}

public sealed class GameRecipe
{
    internal GameRecipe()
    {
    }

    public string AppId { get; internal set; } = "";

    public string Name { get; internal set; } = "";

    public long Revision { get; internal set; }

    public IReadOnlyDictionary<string, IReadOnlyList<string>> Conditions { get; internal set; } = new Dictionary<string, IReadOnlyList<string>>();

    public string Exe { get; internal set; } = "";

    public IReadOnlyList<string> Args { get; internal set; } = Array.Empty<string>();

    public IReadOnlyDictionary<string, string> Ini { get; internal set; } = new Dictionary<string, string>();

    public IReadOnlyList<string> Dependencies { get; internal set; } = Array.Empty<string>();

    public IReadOnlyList<string> SourceUrls { get; internal set; } = Array.Empty<string>();

    public IReadOnlyList<string> TestedGameBuilds { get; internal set; } = Array.Empty<string>();

    public string? TestedAt { get; internal set; }

    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Configuration { get; internal set; } =
        new Dictionary<string, IReadOnlyDictionary<string, string>>();

    public string? RecommendedInput { get; internal set; }

    public string? EffectiveApi { get; internal set; }

    public string QualityOwner { get; internal set; } = "panel";

    public string? RecommendedBuild { get; internal set; }

    public IReadOnlyList<string> OptiScalerRootFiles { get; internal set; } = Array.Empty<string>();

    public bool ReframeworkUpscaler { get; internal set; }

    public bool OptiScalerFrameGeneration { get; internal set; } = true;

    /// <summary>(setting, value) pairs in the game's own words.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> GameSettings { get; internal set; } = Array.Empty<KeyValuePair<string, string>>();

    public string Platform { get; internal set; } = "";

    public string Status { get; internal set; } = "";
}

public sealed class RecipeGame
{
    internal RecipeGame(string appId, string name, IReadOnlyDictionary<string, string> statuses, IReadOnlyDictionary<string, GameRecipe> recipes)
    {
        AppId = appId;
        Name = name;
        Statuses = statuses;
        Recipes = recipes;
    }

    public string AppId { get; }

    public string Name { get; }

    public IReadOnlyDictionary<string, string> Statuses { get; }

    public IReadOnlyDictionary<string, GameRecipe> Recipes { get; }
}

/// <summary>
/// The game recipes (<c>game-recipes/</c>, schema 2, one block per OS), read with the same rules and error codes as
/// <c>py_modules/upscalers/recipe_catalog.py</c>. Files are keyed by their path inside the catalog folder.
/// </summary>
public sealed class RecipeCatalog
{
    public const int MaxFileBytes = 2 * 1024 * 1024;

    private static readonly string[] Platforms = { "linux", "windows" };
    private static readonly HashSet<string> RecipeStatuses = new(StringComparer.Ordinal) { "tested", "untested" };
    private static readonly HashSet<string> EmptyStatuses = new(StringComparer.Ordinal) { "unknown", "not_applicable" };
    private static readonly Dictionary<string, string> PlatformDependencies = new(StringComparer.Ordinal)
    {
        ["proton_dependency"] = "linux",
        ["windows_redist"] = "windows",
    };
    private static readonly HashSet<string> Engines = new(StringComparer.Ordinal) { "optiscaler", "dll", "helixsr", "proton", "mako" };
    private static readonly HashSet<string> Arches = new(StringComparer.Ordinal) { "x86_64", "aarch64" };
    private static readonly HashSet<string> Verbs = new(StringComparer.Ordinal) { "vcrun2022", "msvcrt40" };
    private static readonly HashSet<string> Redistributables = new(StringComparer.Ordinal) { "vc14_x64" };
    private static readonly HashSet<string> PageHosts = new(StringComparer.Ordinal) { "www.nexusmods.com", "nexusmods.com", "github.com", "www.patreon.com" };
    private static readonly HashSet<string> RedistPageHosts = new(StringComparer.Ordinal) { "learn.microsoft.com" };
    // TutorialProgress=4 marks ReShade's tutorial done: otherwise its splash stays over the game until Home is pressed.
    private static readonly Dictionary<string, Dictionary<string, string[]>> AllowedConfiguration = new(StringComparer.Ordinal)
    {
        ["ReShade.ini"] = new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["Luma.SRUserType"] = new[] { "2" },
            ["OVERLAY.TutorialProgress"] = new[] { "4" },
        },
    };
    private static readonly Regex IdentifierPattern = new("^[a-z0-9][a-z0-9-]{0,79}$", RegexOptions.CultureInvariant);
    private static readonly Regex HashPattern = new("^[a-f0-9]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex VersionPattern = new(@"^[0-9]+(?:\.[0-9]+){0,3}$", RegexOptions.CultureInvariant);
    private static readonly Regex GameFilePattern = new(@"^[1-9][0-9]{0,9}\.json$", RegexOptions.CultureInvariant);
    private static readonly Regex AppIdPattern = new("^[1-9][0-9]{0,9}$", RegexOptions.CultureInvariant);
    private static readonly Regex GameBuildPattern = new("^[1-9][0-9]{0,19}$", RegexOptions.CultureInvariant);
    private static readonly Regex ArgumentPattern = new("^--?[A-Za-z0-9][A-Za-z0-9_=.-]*$", RegexOptions.CultureInvariant);
    private static readonly Regex IniKeyPattern = new(@"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$", RegexOptions.CultureInvariant);
    private static readonly Regex BuildIdPattern = new("^[a-z0-9][a-z0-9.-]{0,79}$", RegexOptions.CultureInvariant);
    private static readonly Regex AssetPathPattern = new("^/[^/]+/[^/]+/releases/download/[^/]+/[^/]+$", RegexOptions.CultureInvariant);

    private RecipeCatalog(int catalogVersion, IReadOnlyDictionary<string, RecipeAsset> assets,
        IReadOnlyDictionary<string, RecipeDependency> dependencies, IReadOnlyDictionary<string, RecipeGame> games)
    {
        CatalogVersion = catalogVersion;
        Assets = assets;
        Dependencies = dependencies;
        Games = games;
    }

    public int SchemaVersion => 2;

    public int CatalogVersion { get; }

    public IReadOnlyDictionary<string, RecipeAsset> Assets { get; }

    public IReadOnlyDictionary<string, RecipeDependency> Dependencies { get; }

    public IReadOnlyDictionary<string, RecipeGame> Games { get; }

    public static RecipeCatalog Load(IReadOnlyDictionary<string, byte[]> files)
    {
        var gameFiles = files.Keys.Where(path => path.StartsWith("games/", StringComparison.Ordinal))
            .Select(path => path.Substring("games/".Length))
            .Where(name => !name.StartsWith(".", StringComparison.Ordinal))
            .ToList();
        if (gameFiles.Count > 512 || gameFiles.Any(name => !GameFilePattern.IsMatch(name)))
        {
            throw Error("invalid_game_files");
        }
        var metadata = Object(Read(files, "catalog.json"), new[] { "schema_version", "catalog_version" });
        var rawAssets = Read(files, "assets.json");
        var rawDependencies = Read(files, "dependencies.json");
        var rawGames = gameFiles.Select(name => new KeyValuePair<string, DataValue>(name.Substring(0, name.Length - ".json".Length), Read(files, "games/" + name)))
            .ToList();
        if (!(metadata.Get("schema_version") is DataNumber { Integer: { } schema } && schema == 2))
        {
            throw Error("unsupported_schema");
        }
        var version = (int)Integer(metadata.Get("catalog_version")!, int.MaxValue);
        foreach (var collection in new[] { rawAssets, rawDependencies })
        {
            if (collection is not DataObject { Count: <= 512 })
            {
                throw Error("invalid_collection");
            }
        }
        if (rawGames.Count > 512)
        {
            throw Error("invalid_collection");
        }

        var assets = new Dictionary<string, RecipeAsset>(StringComparer.Ordinal);
        foreach (var member in ((DataObject)rawAssets).Members)
        {
            Identifier(new DataString(member.Key));
            var item = Object(member.Value, new[] { "url", "source_url", "sha256", "size", "filename", "format" });
            if (!(item.Get("sha256") is DataString { Value: var sha } && HashPattern.IsMatch(sha) && item.Get("format") is DataString { Value: "zip" }))
            {
                throw Error("invalid_asset");
            }
            var fileName = SafePath(item.Get("filename")!);
            if (fileName.IndexOf('/') >= 0 || !fileName.EndsWith(".zip", StringComparison.Ordinal))
            {
                throw Error("invalid_filename");
            }
            assets[member.Key] = new RecipeAsset(member.Key, Url(item.Get("url")!, asset: true), Url(item.Get("source_url")!), sha,
                Integer(item.Get("size")!, 2L * 1024 * 1024 * 1024), fileName, "zip");
        }

        var dependencies = new Dictionary<string, RecipeDependency>(StringComparer.Ordinal);
        foreach (var member in ((DataObject)rawDependencies).Members)
        {
            Identifier(new DataString(member.Key));
            dependencies[member.Key] = ReadDependency(member.Key, member.Value, assets);
        }

        var games = new Dictionary<string, RecipeGame>(StringComparer.Ordinal);
        foreach (var raw in rawGames)
        {
            if (!AppIdPattern.IsMatch(raw.Key))
            {
                throw Error("invalid_appid");
            }
            var item = Object(raw.Value, new[] { "name", "linux", "windows" });
            var name = Text(item.Get("name")!, 160);
            var statuses = new Dictionary<string, string>(StringComparer.Ordinal);
            var recipes = new Dictionary<string, GameRecipe>(StringComparer.Ordinal);
            foreach (var platform in Platforms)
            {
                var block = item.Get(platform)!;
                var status = block is DataObject blockObject && blockObject.Get("status") is DataString statusText ? statusText.Value : null;
                if (status is not null && EmptyStatuses.Contains(status))
                {
                    Object(block, new[] { "status" });
                }
                else if (status is not null && RecipeStatuses.Contains(status))
                {
                    recipes[platform] = ReadRecipe(raw.Key, name, platform, block, dependencies);
                }
                else
                {
                    throw Error("invalid_status");
                }
                statuses[platform] = status;
            }
            games[raw.Key] = new RecipeGame(raw.Key, name, statuses, recipes);
        }

        var catalog = new RecipeCatalog(version, assets, dependencies, games);
        catalog.DependencyOrder(dependencies.Keys.ToList());
        return catalog;
    }

    /// <summary>
    /// The recipe this system uses for the game, or null. <paramref name="arch"/> takes Windows' names too
    /// (<c>amd64</c>, <c>arm64</c>).
    /// </summary>
    public GameRecipe? Match(string appId, string engine, string platform, string arch, string? gameBuild = null)
    {
        if (!Games.TryGetValue(appId, out var game) || !game.Recipes.TryGetValue(platform.ToLowerInvariant(), out var entry))
        {
            return null;
        }
        if (entry.Conditions.TryGetValue("game_builds", out var builds) && (gameBuild is null || !builds.Contains(gameBuild)))
        {
            return null;
        }
        arch = arch.ToLowerInvariant();
        arch = arch switch { "amd64" => "x86_64", "arm64" => "aarch64", _ => arch };
        return entry.Conditions["engine"].Contains(engine) && entry.Conditions["arch"].Contains(arch) ? entry : null;
    }

    /// <summary>
    /// Dependencies in install order. With a platform, requirements that belong to another system are skipped: a
    /// shared mod may need one runtime under Proton and another on Windows.
    /// </summary>
    public IReadOnlyList<RecipeDependency> DependencyOrder(IReadOnlyList<string> ids, string? platform = null)
    {
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var active = new HashSet<string>(StringComparer.Ordinal);
        var ordered = new List<RecipeDependency>();

        void Visit(string id)
        {
            if (active.Contains(id) || !Dependencies.ContainsKey(id))
            {
                throw Error("dependency_cycle_or_missing");
            }
            if (visited.Contains(id))
            {
                return;
            }
            active.Add(id);
            var dependency = Dependencies[id];
            foreach (var child in dependency.Requires)
            {
                if (platform is not null && Foreign(Dependencies.TryGetValue(child, out var required) ? required : null, platform))
                {
                    continue;
                }
                Visit(child);
            }
            active.Remove(id);
            visited.Add(id);
            ordered.Add(dependency);
        }

        foreach (var id in ids)
        {
            Visit(id);
        }
        return ordered;
    }

    private static bool Foreign(RecipeDependency? dependency, string platform) =>
        dependency is not null && PlatformDependencies.TryGetValue(dependency.Kind, out var owner) && owner != platform;

    private static List<RecipeDependency> Closure(IEnumerable<string> ids, IReadOnlyDictionary<string, RecipeDependency> dependencies, string platform)
    {
        var seen = new Dictionary<string, RecipeDependency>(StringComparer.Ordinal);
        var pending = new Stack<string>(ids);
        while (pending.Count > 0)
        {
            var id = pending.Pop();
            if (seen.ContainsKey(id) || !dependencies.TryGetValue(id, out var dependency))
            {
                continue;
            }
            seen[id] = dependency;
            foreach (var child in dependency.Requires.Where(child => !Foreign(dependencies.TryGetValue(child, out var required) ? required : null, platform)))
            {
                pending.Push(child);
            }
        }
        return seen.Values.ToList();
    }

    private static RecipeDependency ReadDependency(string id, DataValue value, IReadOnlyDictionary<string, RecipeAsset> assets)
    {
        var kind = value is DataObject withKind && withKind.Get("kind") is DataString kindText ? kindText.Value : null;
        var dependency = new RecipeDependency { Id = id, Kind = kind ?? "" };
        switch (kind)
        {
            case "game_files":
            {
                var item = Object(value, new[] { "kind", "asset", "files" }, new[] { "requires" });
                if (!(item.Get("asset") is DataString { Value: var asset } && assets.ContainsKey(asset)
                      && item.Get("files") is DataObject { Count: > 0 and <= 2048 }))
                {
                    throw Error("invalid_file_dependency");
                }
                var files = PathMap((DataObject)item.Get("files")!);
                if (files.Keys.Select(name => name.ToLowerInvariant()).Distinct(StringComparer.Ordinal).Count() != files.Count)
                {
                    throw Error("duplicate_destination");
                }
                dependency.Asset = asset;
                dependency.Files = files;
                dependency.Requires = Strings(item.Get("requires") ?? EmptyArray, Identifier);
                return dependency;
            }
            case "proton_dependency":
            {
                var item = Object(value, new[] { "kind", "provider", "verb" }, new[] { "requires" });
                if (!(item.Get("provider") is DataString { Value: "winetricks" } && item.Get("verb") is DataString { Value: var verb } && Verbs.Contains(verb)))
                {
                    throw Error("unsupported_dependency");
                }
                dependency.Provider = "winetricks";
                dependency.Verb = verb;
                dependency.Requires = Strings(item.Get("requires") ?? EmptyArray, Identifier);
                return dependency;
            }
            case "windows_redist":
            {
                var item = Object(value, new[] { "kind", "provider", "component", "min_version", "page_url" }, new[] { "requires" });
                if (!(item.Get("provider") is DataString { Value: "microsoft" } && item.Get("component") is DataString { Value: var component }
                      && Redistributables.Contains(component)))
                {
                    throw Error("unsupported_dependency");
                }
                dependency.Provider = "microsoft";
                dependency.Verb = component;
                dependency.Requires = Strings(item.Get("requires") ?? EmptyArray, Identifier);
                dependency.Version = Version(item.Get("min_version")!);
                dependency.PageUrl = PageUrl(item.Get("page_url")!, RedistPageHosts);
                return dependency;
            }
            case "user_files":
            {
                var item = Object(value, new[] { "kind", "name", "page_url", "version", "files" }, new[] { "avoid_versions", "requires", "download_url" });
                if (item.Get("files") is not DataObject { Count: > 0 and <= 32 })
                {
                    throw Error("invalid_file_dependency");
                }
                var files = PathMap((DataObject)item.Get("files")!);
                if (files.Values.Any(member => member.IndexOf('/') >= 0)
                    || files.Keys.Select(name => name.ToLowerInvariant()).Distinct(StringComparer.Ordinal).Count() != files.Count)
                {
                    throw Error("invalid_file_dependency");
                }
                dependency.Files = files;
                dependency.Requires = Strings(item.Get("requires") ?? EmptyArray, Identifier);
                dependency.Name = Text(item.Get("name")!, 80);
                dependency.PageUrl = PageUrl(item.Get("page_url")!, PageHosts);
                dependency.Version = Version(item.Get("version")!);
                dependency.AvoidVersions = Strings(item.Get("avoid_versions") ?? EmptyArray, Version, 16);
                dependency.DownloadUrl = item.Get("download_url") is { } download ? PageUrl(download, PageHosts) : null;
                return dependency;
            }
            default:
                throw Error("unsupported_dependency");
        }
    }

    private static GameRecipe ReadRecipe(string appId, string name, string platform, DataValue value, IReadOnlyDictionary<string, RecipeDependency> dependencies)
    {
        var item = Object(value,
            new[] { "status", "revision", "conditions", "exe", "args", "ini", "dependencies", "source_urls" },
            new[] { "tested_game_builds", "tested_at", "configuration", "recommended_input", "effective_api", "quality_owner", "recommended_build",
                "optiscaler_root_files", "reframework_upscaler", "optiscaler_fg", "game_settings" });
        var conditions = Object(item.Get("conditions")!, new[] { "engine", "arch" }, new[] { "game_builds" });
        var parsedConditions = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var member in conditions.Members)
        {
            if (member.Key == "game_builds")
            {
                var builds = Strings(member.Value, GameBuild);
                if (builds.Count == 0)
                {
                    throw Error("invalid_conditions");
                }
                parsedConditions[member.Key] = builds;
                continue;
            }
            var values = Strings(member.Value, entry => Text(entry), 8);
            var allowed = member.Key == "engine" ? Engines : Arches;
            if (values.Count == 0 || !values.All(allowed.Contains))
            {
                throw Error("invalid_conditions");
            }
            parsedConditions[member.Key] = values;
        }
        var args = Strings(item.Get("args")!, entry => Text(entry, 128), 16);
        if (args.Any(argument => !ArgumentPattern.IsMatch(argument)))
        {
            throw Error("invalid_game_argument");
        }
        if (item.Get("ini") is not DataObject { Count: <= 128 } settings)
        {
            throw Error("invalid_ini");
        }
        var ini = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var member in settings.Members)
        {
            if (!IniKeyPattern.IsMatch(member.Key))
            {
                throw Error("invalid_ini_key");
            }
            ini[member.Key] = Text(member.Value, 256);
        }
        var ids = Strings(item.Get("dependencies")!, Identifier);
        if (!ids.All(dependencies.ContainsKey))
        {
            throw Error("missing_dependency");
        }
        if (ids.Any(id => Foreign(dependencies[id], platform)) || Closure(ids, dependencies, platform).Any(dependency => Foreign(dependency, platform)))
        {
            throw Error("dependency_not_for_platform");
        }
        var sources = Strings(item.Get("source_urls")!, entry => Url(entry), 16);
        if (sources.Count == 0)
        {
            throw Error("missing_source");
        }
        var configuration = ReadConfiguration(item.Get("configuration"));
        foreach (var (key, allowed) in new[] { ("effective_api", new[] { "d3d11", "d3d12", "vulkan" }), ("quality_owner", new[] { "panel", "game" }) })
        {
            if (item.Get(key) is { } field && !(field is DataString { Value: var text } && allowed.Contains(text)))
            {
                throw Error("invalid_" + key);
            }
        }
        if (item.Get("recommended_input") is { } input && !(input is DataString { Value: "dlss" or "fsr31" or "fsr2" or "xess" }))
        {
            throw Error("invalid_recommended_input");
        }
        if (item.Get("recommended_build") is { } recommended && !(recommended is DataString { Value: var buildId } && BuildIdPattern.IsMatch(buildId)))
        {
            throw Error("invalid_recommended_build");
        }
        var rootFiles = Strings(item.Get("optiscaler_root_files") ?? EmptyArray, SafePath, 8);
        if (rootFiles.Any(file => file.IndexOf('/') >= 0 || !file.ToLowerInvariant().EndsWith(".dll", StringComparison.Ordinal)))
        {
            throw Error("invalid_root_files");
        }
        var flags = new Dictionary<string, bool>(StringComparer.Ordinal);
        foreach (var (key, fallback) in new[] { ("reframework_upscaler", false), ("optiscaler_fg", true) })
        {
            var field = item.Get(key);
            if (field is not null && field is not DataBool)
            {
                throw Error("invalid_" + key);
            }
            flags[key] = field is DataBool flag ? flag.Value : fallback;
        }
        if (item.Get("game_settings") is { } rawSettings && rawSettings is not DataArray { Items.Count: <= 8 })
        {
            throw Error("invalid_game_settings");
        }
        var gameSettings = ((item.Get("game_settings") as DataArray)?.Items ?? Array.Empty<DataValue>())
            .Select(entry => Object(entry, new[] { "setting", "value" }))
            .Select(entry => new KeyValuePair<string, string>(Text(entry.Get("setting")!, 80), Text(entry.Get("value")!, 40)))
            .ToList();
        var testedBuilds = Strings(item.Get("tested_game_builds") ?? EmptyArray, GameBuild);
        string? testedAt = null;
        if (item.Get("tested_at") is { } testedField && testedField is not DataNull)
        {
            if (!(testedField is DataString { Value: var date } && DateTime.TryParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _)
                  && testedBuilds.Count > 0))
            {
                throw Error("invalid_test_date");
            }
            testedAt = date;
        }
        return new GameRecipe
        {
            AppId = appId,
            Name = name,
            Revision = Integer(item.Get("revision")!, int.MaxValue),
            Conditions = parsedConditions,
            Exe = SafePath(item.Get("exe")!),
            Args = args,
            Ini = ini,
            Dependencies = ids,
            SourceUrls = sources,
            TestedGameBuilds = testedBuilds,
            TestedAt = testedAt,
            Configuration = configuration,
            RecommendedInput = (item.Get("recommended_input") as DataString)?.Value,
            EffectiveApi = (item.Get("effective_api") as DataString)?.Value,
            QualityOwner = (item.Get("quality_owner") as DataString)?.Value ?? "panel",
            RecommendedBuild = (item.Get("recommended_build") as DataString)?.Value,
            OptiScalerRootFiles = rootFiles,
            ReframeworkUpscaler = flags["reframework_upscaler"],
            OptiScalerFrameGeneration = flags["optiscaler_fg"],
            GameSettings = gameSettings,
            Platform = platform,
            Status = ((DataString)((DataObject)value).Get("status")!).Value,
        };
    }

    private static IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> ReadConfiguration(DataValue? value)
    {
        var result = new Dictionary<string, IReadOnlyDictionary<string, string>>(StringComparer.Ordinal);
        if (value is null)
        {
            return result;
        }
        if (value is not DataObject configuration || configuration.Keys.Any(key => !AllowedConfiguration.ContainsKey(key)))
        {
            throw Error("unsupported_configuration");
        }
        foreach (var member in configuration.Members)
        {
            SafePath(new DataString(member.Key));
            var allowed = AllowedConfiguration[member.Key];
            if (member.Value is not DataObject { Count: > 0 } changes || changes.Keys.Any(key => !allowed.ContainsKey(key)))
            {
                throw Error("unsupported_configuration");
            }
            if (changes.Members.Any(change => !(change.Value is DataString { Value: var text } && allowed[change.Key].Contains(text))))
            {
                throw Error("unsupported_configuration");
            }
            result[member.Key] = changes.Members.ToDictionary(change => change.Key, change => ((DataString)change.Value).Value, StringComparer.Ordinal);
        }
        return result;
    }

    private static readonly DataArray EmptyArray = new(Array.Empty<DataValue>());

    private static DataFormatException Error(string code) => new(code);

    private static DataValue Read(IReadOnlyDictionary<string, byte[]> files, string path)
    {
        if (!files.TryGetValue(path, out var bytes) || bytes.Length > MaxFileBytes)
        {
            throw Error("invalid_catalog_file");
        }
        return DataValue.Parse(bytes);
    }

    private static DataObject Object(DataValue value, IReadOnlyCollection<string> required, IReadOnlyCollection<string>? optional = null) =>
        BuildCatalog.Fields(value, required, optional);

    private static int CodePoints(string value)
    {
        var count = value.Length;
        for (var index = 0; index + 1 < value.Length; index++)
        {
            if (char.IsHighSurrogate(value[index]) && char.IsLowSurrogate(value[index + 1]))
            {
                count--;
                index++;
            }
        }
        return count;
    }

    private static string Text(DataValue value, int limit = 512)
    {
        if (value is not DataString { Value: var text } || text.Length == 0 || CodePoints(text) > limit || text.Any(character => character < ' '))
        {
            throw Error("invalid_text");
        }
        return text;
    }

    private static long Integer(DataValue value, long maximum)
    {
        if (value is not DataNumber { Integer: { } number } || number <= BigInteger.Zero || number > maximum)
        {
            throw Error("invalid_number");
        }
        return (long)number;
    }

    private static string GameBuild(DataValue value) =>
        value is DataString { Value: var text } && GameBuildPattern.IsMatch(text) ? text : throw Error("invalid_game_build");

    private static string Identifier(DataValue value) =>
        value is DataString { Value: var text } && IdentifierPattern.IsMatch(text) ? text : throw Error("invalid_id");

    private static string Version(DataValue value) =>
        value is DataString { Value: var text } && VersionPattern.IsMatch(text) ? text : throw Error("invalid_version");

    private static string SafePath(DataValue value)
    {
        var text = Text(value);
        var parts = text.Split('/');
        if (text.StartsWith("/", StringComparison.Ordinal) || text.IndexOf('\\') >= 0 || text.IndexOf(':') >= 0 || parts.Any(part => part is "" or "." or ".."))
        {
            throw Error("unsafe_path");
        }
        return text;
    }

    private static Dictionary<string, string> PathMap(DataObject files)
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var member in files.Members)
        {
            var destination = SafePath(new DataString(member.Key));
            map[destination] = SafePath(member.Value);
        }
        return map;
    }

    private static IReadOnlyList<string> Strings(DataValue value, Func<DataValue, string> validate, int maximum = 128)
    {
        if (value is not DataArray { Items.Count: var count } array || count > maximum)
        {
            throw Error("invalid_list");
        }
        var result = array.Items.Select(validate).ToList();
        if (result.Distinct(StringComparer.Ordinal).Count() != result.Count)
        {
            throw Error("duplicate_value");
        }
        return result;
    }

    private static string Url(DataValue value) => Url(value, asset: false);

    private static string Url(DataValue value, bool asset)
    {
        var text = Text(value, 2048);
        var parts = UrlParts.Split(text);
        if (parts is null || parts.Scheme != "https" || parts.HostName != "github.com" || parts.HasUserInfo || parts.Port is not null
            || parts.Query.Length > 0 || parts.Fragment.Length > 0)
        {
            throw Error("untrusted_origin");
        }
        if (asset && !AssetPathPattern.IsMatch(parts.Path))
        {
            throw Error("untrusted_asset_path");
        }
        return text;
    }

    private static string PageUrl(DataValue value, HashSet<string> hosts)
    {
        var text = Text(value, 2048);
        var parts = UrlParts.Split(text);
        if (parts is null || parts.Scheme != "https" || parts.HostName is null || !hosts.Contains(parts.HostName) || parts.HasUserInfo || parts.Port is not null)
        {
            throw Error("untrusted_origin");
        }
        return text;
    }
}

/// <summary>The parts of a URL as Python's <c>urllib.parse.urlsplit</c> reports them; null where it raises.</summary>
internal sealed class UrlParts
{
    private UrlParts(string scheme, string? hostName, bool hasUserInfo, int? port, string path, string query, string fragment)
    {
        Scheme = scheme;
        HostName = hostName;
        HasUserInfo = hasUserInfo;
        Port = port;
        Path = path;
        Query = query;
        Fragment = fragment;
    }

    public string Scheme { get; }

    public string? HostName { get; }

    public bool HasUserInfo { get; }

    public int? Port { get; }

    public string Path { get; }

    public string Query { get; }

    public string Fragment { get; }

    public static UrlParts? Split(string url)
    {
        url = new string(url.TrimStart(Enumerable.Range(0, 33).Select(code => (char)code).ToArray()).Where(c => c is not '\t' and not '\r' and not '\n').ToArray());
        var scheme = "";
        var colon = url.IndexOf(':');
        if (colon > 0 && char.IsLetter(url[0]) && url.Substring(0, colon).All(c => c < 128 && (char.IsLetterOrDigit(c) || c is '+' or '-' or '.')))
        {
            scheme = url.Substring(0, colon).ToLowerInvariant();
            url = url.Substring(colon + 1);
        }
        var netloc = "";
        if (url.StartsWith("//", StringComparison.Ordinal))
        {
            var end = url.IndexOfAny(new[] { '/', '?', '#' }, 2);
            if (end < 0)
            {
                end = url.Length;
            }
            netloc = url.Substring(2, end - 2);
            url = url.Substring(end);
        }
        var fragment = "";
        var hash = url.IndexOf('#');
        if (hash >= 0)
        {
            fragment = url.Substring(hash + 1);
            url = url.Substring(0, hash);
        }
        var query = "";
        var question = url.IndexOf('?');
        if (question >= 0)
        {
            query = url.Substring(question + 1);
            url = url.Substring(0, question);
        }
        var at = netloc.LastIndexOf('@');
        var hostInfo = at >= 0 ? netloc.Substring(at + 1) : netloc;
        string host;
        string? port = null;
        if (hostInfo.StartsWith("[", StringComparison.Ordinal))
        {
            var close = hostInfo.IndexOf(']');
            host = close >= 0 ? hostInfo.Substring(1, close - 1) : hostInfo.Substring(1);
            var rest = close >= 0 ? hostInfo.Substring(close + 1) : "";
            if (rest.StartsWith(":", StringComparison.Ordinal))
            {
                port = rest.Substring(1);
            }
        }
        else
        {
            var portAt = hostInfo.IndexOf(':');
            host = portAt >= 0 ? hostInfo.Substring(0, portAt) : hostInfo;
            port = portAt >= 0 ? hostInfo.Substring(portAt + 1) : null;
        }
        int? portNumber = null;
        if (port is not null)
        {
            if (port.Length == 0 || !port.All(c => c is >= '0' and <= '9') || !int.TryParse(port, NumberStyles.None, CultureInfo.InvariantCulture, out var number)
                || number > 65535)
            {
                return null;
            }
            portNumber = number;
        }
        return new UrlParts(scheme, host.Length == 0 ? null : host.ToLowerInvariant(), at >= 0, portNumber, url, query, fragment);
    }
}
