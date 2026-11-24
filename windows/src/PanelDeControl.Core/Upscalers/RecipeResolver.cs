using System.Globalization;
using PanelDeControl.Core.Data;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// What installing needs for one game once the catalog row, the OptiScaler wiki and the engine rules are composed:
/// the same fields as <c>recipes.Recipe</c> in <c>py_modules/upscalers/recipes.py</c>.
/// </summary>
public sealed class ResolvedRecipe
{
    internal ResolvedRecipe(string appId)
    {
        AppId = appId;
    }

    public string AppId { get; }

    public string? Exe { get; internal set; }

    public IReadOnlyList<string> Args { get; internal set; } = Array.Empty<string>();

    /// <summary>Destination beside the exe to the id of a build catalog asset.</summary>
    public IReadOnlyDictionary<string, string> Files { get; internal set; } = new Dictionary<string, string>();

    public IReadOnlyList<string> NativeDlls { get; internal set; } = Array.Empty<string>();

    public IReadOnlyDictionary<string, string> Ini { get; internal set; } = new Dictionary<string, string>();

    public string? FgNote { get; internal set; }

    public string? Proxy { get; internal set; }

    public IReadOnlyList<string> Needs { get; internal set; } = Array.Empty<string>();

    public bool Broken { get; internal set; }

    public bool OptiPatcher { get; internal set; }

    /// <summary>Panel's live-panel key for OptiScaler's menu when the game already uses Insert.</summary>
    public string? MenuKey { get; internal set; }

    /// <summary>The wiki's verdict: works, broken or partial.</summary>
    public string? Status { get; internal set; }

    public IReadOnlyList<string> Inputs { get; internal set; } = Array.Empty<string>();

    public string? Page { get; internal set; }

    public bool Linux { get; internal set; }

    /// <summary><c>Key=value</c> pairs of OptiScaler.ini from the game's wiki page.</summary>
    public IReadOnlyDictionary<string, string> WikiSettings { get; internal set; } = new Dictionary<string, string>();

    public IReadOnlyDictionary<string, string> WikiSuggestions { get; internal set; } = new Dictionary<string, string>();

    /// <summary><c>game-recipes</c>, or the wiki's own label when the game only has a wiki row.</summary>
    public string Source { get; internal set; } = "panel";

    public IReadOnlyList<string> Dependencies { get; internal set; } = Array.Empty<string>();

    public long? CatalogRevision { get; internal set; }

    public int? CatalogVersion { get; internal set; }

    public string? RecommendedInput { get; internal set; }

    public string? EffectiveApi { get; internal set; }

    public string QualityOwner { get; internal set; } = "panel";

    public string? RecommendedBuild { get; internal set; }

    public IReadOnlyList<string> OptiScalerRootFiles { get; internal set; } = Array.Empty<string>();

    public bool ReframeworkUpscaler { get; internal set; }

    public bool OptiScalerFrameGeneration { get; internal set; } = true;

    public IReadOnlyList<KeyValuePair<string, string>> GameSettings { get; internal set; } = Array.Empty<KeyValuePair<string, string>>();

    public IReadOnlyList<KeyValuePair<string, string>> AnrSettings { get; internal set; } = Array.Empty<KeyValuePair<string, string>>();

    public KeyValuePair<string, string>? ModLaunchExe { get; internal set; }

    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> ModSettings { get; internal set; } =
        new Dictionary<string, IReadOnlyDictionary<string, string>>();

    public string? ModFrameGeneration { get; internal set; }

    public bool ProtectDlls { get; internal set; }

    public IReadOnlyList<GameConfigChange> GameConfig { get; internal set; } = Array.Empty<GameConfigChange>();

    public bool LegacyFfxSwap { get; internal set; } = true;

    internal ResolvedRecipe Copy() => (ResolvedRecipe)MemberwiseClone();
}

/// <summary>The OptiScaler wiki's per-game facts (<c>py_modules/upscalers/recipes_wiki.json</c>), as the Linux backend reads them.</summary>
public sealed class WikiRecipes
{
    private static readonly HashSet<string> Needs = new(StringComparer.Ordinal) { "reframework", "nvngx_dlss", "anti_cheat_off", "luma", "mod" };
    private static readonly HashSet<string> Statuses = new(StringComparer.Ordinal) { "works", "broken", "partial" };
    private readonly Dictionary<string, ResolvedRecipe> recipes;

    private WikiRecipes(Dictionary<string, ResolvedRecipe> recipes)
    {
        this.recipes = recipes;
    }

    public static WikiRecipes Empty { get; } = new(new Dictionary<string, ResolvedRecipe>(StringComparer.Ordinal));

    /// <summary>An unreadable or malformed file gives no wiki facts, like the Linux backend.</summary>
    public static WikiRecipes Load(byte[]? json)
    {
        if (json is null)
        {
            return Empty;
        }
        DataObject? root;
        try
        {
            root = DataValue.Parse(json) as DataObject;
        }
        catch (DataFormatException)
        {
            return Empty;
        }
        if (root is null)
        {
            return Empty;
        }
        var source = root.Get("source") is DataString { Value.Length: > 0 } label ? label.Value : "optiscaler-wiki";
        var loaded = new Dictionary<string, ResolvedRecipe>(StringComparer.Ordinal);
        foreach (var member in (root.Get("recipes") as DataObject)?.Members ?? Array.Empty<KeyValuePair<string, DataValue>>())
        {
            if (member.Key.Length == 0 || !member.Key.All(char.IsDigit) || member.Value is not DataObject entry)
            {
                continue;
            }
            if (FromFacts(member.Key, entry, source) is { } recipe)
            {
                loaded[member.Key] = recipe;
            }
        }
        return new WikiRecipes(loaded);
    }

    internal ResolvedRecipe? Get(string appId) => recipes.TryGetValue(appId, out var recipe) ? recipe : null;

    private static ResolvedRecipe? FromFacts(string appId, DataObject entry, string source)
    {
        var page = entry.Get("page_facts") as DataObject ?? new DataObject(Array.Empty<KeyValuePair<string, DataValue>>());
        var proxy = entry.Get("proxy") as DataString ?? page.Get("proxy") as DataString;
        var status = entry.Get("status") is DataString { Value: var verdict } && Statuses.Contains(verdict) ? verdict : null;
        var args = Items(entry.Get("args")).OfType<DataString>().Where(text => text.Value == "-dx12").Select(text => text.Value).ToList();
        var needs = Items(entry.Get("needs")).Concat(Items(page.Get("needs")))
            .OfType<DataString>().Select(text => text.Value).Where(Needs.Contains).Distinct(StringComparer.Ordinal).ToList();
        var recipe = new ResolvedRecipe(appId)
        {
            Args = args,
            Proxy = proxy?.Value,
            Needs = needs,
            Broken = status == "broken",
            OptiPatcher = Truthy(entry.Get("optipatcher")),
            Status = status,
            Inputs = Items(entry.Get("inputs")).OfType<DataString>().Select(text => Truncate(text.Value, 12)).Take(9).ToList(),
            Page = entry.Get("page") is DataString pageName ? Truncate(pageName.Value, 120) : null,
            Linux = Truthy(page.Get("linux")),
            WikiSettings = Pairs(page.Get("settings")),
            WikiSuggestions = Pairs(page.Get("suggestions")),
            Source = source,
        };
        return recipe.Status is not null || recipe.Args.Count > 0 || !string.IsNullOrEmpty(recipe.Proxy) || recipe.Needs.Count > 0 || recipe.OptiPatcher
            ? recipe
            : null;
    }

    private static IReadOnlyList<DataValue> Items(DataValue? value) => (value as DataArray)?.Items ?? Array.Empty<DataValue>();

    private static bool Truthy(DataValue? value) => value switch
    {
        DataBool flag => flag.Value,
        DataString text => text.Value.Length > 0,
        DataNumber number => number.Integer is { } integer ? !integer.IsZero : number.Real != 0,
        DataArray array => array.Items.Count > 0,
        DataObject map => map.Count > 0,
        _ => false,
    };

    private static IReadOnlyDictionary<string, string> Pairs(DataValue? value)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        if (value is not DataObject map)
        {
            return result;
        }
        foreach (var member in map.Members)
        {
            var bare = member.Key.Replace("_", "");
            if (bare.Length > 0 && bare.All(char.IsLetterOrDigit))
            {
                result[Truncate(member.Key, 64)] = Truncate(Text(member.Value), 64);
            }
        }
        return result;
    }

    private static string Text(DataValue value) => value switch
    {
        DataString text => text.Value,
        DataBool flag => flag.Value ? "True" : "False",
        DataNumber { Integer: { } integer } => integer.ToString(CultureInfo.InvariantCulture),
        DataNumber number => number.Real.ToString("R", CultureInfo.InvariantCulture),
        _ => "None",
    };

    private static string Truncate(string text, int codePoints)
    {
        var count = 0;
        for (var index = 0; index < text.Length; index++)
        {
            if (count == codePoints)
            {
                return text.Substring(0, index);
            }
            count++;
            if (char.IsHighSurrogate(text[index]) && index + 1 < text.Length && char.IsLowSurrogate(text[index + 1]))
            {
                index++;
            }
        }
        return text;
    }
}

/// <summary>
/// The recipe for a game on this system: its <c>game-recipes</c> row, the OptiScaler wiki's facts and the RE Engine rule,
/// composed exactly as <c>recipes.recipe_for</c> and <c>recipes.with_engine</c> do on Linux. Fetching the live wiki is not part of it.
/// </summary>
public sealed class RecipeResolver
{
    /// <summary>Every RE Engine game ships its packs as this file in the game root.</summary>
    public const string ReEngineMarker = "re_chunk_000.pak";

    private const string ReframeworkAsset = "reframework-nightly";
    private const string ReframeworkFile = "dinput8.dll";
    private readonly RecipeCatalog? catalog;
    private readonly WikiRecipes wiki;

    public RecipeResolver(RecipeCatalog? catalog, WikiRecipes? wiki = null)
    {
        this.catalog = catalog;
        this.wiki = wiki ?? WikiRecipes.Empty;
    }

    /// <summary>Null when neither the catalog nor the wiki knows the game and nothing in its folder asks for a rule.</summary>
    public ResolvedRecipe? Resolve(string appId, string engine, string platform, string arch, string? gameBuild,
        IReadOnlyFileSystem fileSystem, string gameRoot)
    {
        ResolvedRecipe? curated = null;
        if (catalog?.Match(appId, engine, platform, arch, gameBuild) is { } entry)
        {
            curated = FromEntry(entry, engine, catalog.CatalogVersion);
        }
        return WithEngine(Combine(curated, wiki.Get(appId)), appId, fileSystem, gameRoot);
    }

    private static ResolvedRecipe FromEntry(GameRecipe entry, string engine, int catalogVersion)
    {
        var needs = entry.Needs.ToList();
        if (entry.Dependencies.Any(id => id.StartsWith("luma-", StringComparison.Ordinal)) && !needs.Contains("luma"))
        {
            needs.Add("luma");
        }
        return new ResolvedRecipe(entry.AppId)
        {
            Exe = entry.Exe,
            Args = entry.Args,
            Ini = Copy(entry.Ini),
            Proxy = entry.Proxy,
            ProtectDlls = entry.ProtectDlls,
            LegacyFfxSwap = entry.LegacyFfxSwap,
            Files = Copy(entry.Files),
            NativeDlls = entry.NativeDlls,
            Needs = needs,
            AnrSettings = entry.AnrSettings,
            GameConfig = entry.GameConfig,
            ModLaunchExe = entry.ModLaunchExe,
            ModSettings = entry.ModSettings,
            ModFrameGeneration = entry.ModFrameGeneration,
            FgNote = entry.FgNote,
            Dependencies = entry.Dependencies,
            CatalogRevision = entry.Revision,
            CatalogVersion = catalogVersion,
            Source = "game-recipes",
            RecommendedInput = engine == "optiscaler" ? entry.RecommendedInput : null,
            EffectiveApi = entry.EffectiveApi,
            QualityOwner = entry.QualityOwner,
            RecommendedBuild = entry.RecommendedBuild,
            OptiScalerRootFiles = entry.OptiScalerRootFiles,
            ReframeworkUpscaler = entry.ReframeworkUpscaler,
            OptiScalerFrameGeneration = entry.OptiScalerFrameGeneration,
            GameSettings = entry.GameSettings,
        };
    }

    private static Dictionary<string, string> Copy(IReadOnlyDictionary<string, string> source)
    {
        var copy = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var pair in source)
        {
            copy[pair.Key] = pair.Value;
        }
        return copy;
    }

    /// <summary>A curated recipe keeps its own steps and gains what the wiki knows about the game.</summary>
    private static ResolvedRecipe? Combine(ResolvedRecipe? curated, ResolvedRecipe? facts)
    {
        if (curated is null || facts is null)
        {
            return curated ?? facts;
        }
        var merged = curated.Copy();
        merged.Proxy = string.IsNullOrEmpty(curated.Proxy) ? facts.Proxy : curated.Proxy;
        merged.Args = curated.Args.Count > 0 ? curated.Args : facts.Args;
        merged.Needs = curated.Needs.Concat(facts.Needs).Distinct(StringComparer.Ordinal).ToList();
        merged.Broken = curated.Broken || facts.Broken;
        merged.OptiPatcher = curated.OptiPatcher || facts.OptiPatcher;
        merged.Status = facts.Status;
        merged.Inputs = facts.Inputs;
        merged.Page = facts.Page;
        merged.Linux = facts.Linux;
        merged.WikiSettings = facts.WikiSettings
            .Where(setting => !curated.Ini.Keys.Any(key => key.EndsWith("." + setting.Key, StringComparison.Ordinal)))
            .ToDictionary(setting => setting.Key, setting => setting.Value, StringComparer.Ordinal);
        merged.WikiSuggestions = facts.WikiSuggestions;
        return merged;
    }

    private ResolvedRecipe? WithEngine(ResolvedRecipe? recipe, string appId, IReadOnlyFileSystem fileSystem, string gameRoot)
    {
        if (!fileSystem.IsFile(FileSystemPath.Join(gameRoot, ReEngineMarker)) && !(recipe is not null && recipe.Needs.Contains("reframework")))
        {
            return recipe;
        }
        var result = (recipe ?? new ResolvedRecipe(appId)).Copy();
        var ini = Copy(result.Ini);
        ini["Menu.ShortcutKey"] = "0x24";
        var files = Copy(result.Files);
        var placed = new HashSet<string>(files.Keys.Concat(DependencyFiles(result)).Select(name => name.ToLowerInvariant()), StringComparer.Ordinal);
        if (!files.Values.Contains(ReframeworkAsset) && !placed.Contains(ReframeworkFile))
        {
            files[ReframeworkFile] = ReframeworkAsset;
            placed.Add(ReframeworkFile);
        }
        var nativeDlls = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var name in result.NativeDlls.Concat(placed.Contains(ReframeworkFile) ? new[] { "dinput8" } : Array.Empty<string>()))
        {
            var key = name.ToLowerInvariant();
            if (!nativeDlls.ContainsKey(key))
            {
                nativeDlls[key] = name;
            }
        }
        result.Ini = ini;
        result.MenuKey = "home";
        result.Files = files;
        result.NativeDlls = nativeDlls.Values.ToList();
        result.Needs = result.Needs.Where(need => need != "reframework").ToList();
        return result;
    }

    /// <summary>Files a curated recipe's dependencies place, e.g. the pd-upscaler REFramework build some games need.</summary>
    private IEnumerable<string> DependencyFiles(ResolvedRecipe recipe)
    {
        if (catalog is null)
        {
            return Array.Empty<string>();
        }
        try
        {
            return catalog.DependencyOrder(recipe.Dependencies).SelectMany(dependency => dependency.Files.Keys).ToList();
        }
        catch (DataFormatException)
        {
            return Array.Empty<string>();
        }
    }
}
