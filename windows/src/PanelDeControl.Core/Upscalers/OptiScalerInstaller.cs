using System.Text;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What Panel left in a game, kept by the caller so it can replace or remove it later.</summary>
public sealed class InstalledUpscaler
{
    public string Build { get; set; } = "";

    public string Archive { get; set; } = "";

    public string Engine { get; set; } = "optiscaler";

    public string Proxy { get; set; } = "";

    public string Target { get; set; } = "";

    public string? Exe { get; set; }

    public UpscalerChoice Options { get; set; } = new();

    public string? FrameGenRoute { get; set; }

    /// <summary>The game libraries the DLL mode swapped, relative to <see cref="Target"/>.</summary>
    public IReadOnlyList<string> DllTargets { get; set; } = Array.Empty<string>();

    /// <summary>Whether the Apex Neural Rendering FG add-on went in beside OptiScaler.</summary>
    public bool Anr { get; set; }

    /// <summary>Launch arguments the game's recipe asks for on Windows.</summary>
    public IReadOnlyList<string> Args { get; set; } = Array.Empty<string>();

    /// <summary>The arguments Panel itself added to Steam's launch options, and only those come out on removal.</summary>
    public IReadOnlyList<string> AddedArgs { get; set; } = Array.Empty<string>();

    /// <summary>OptiScaler.ini keys Panel owns, sorted as Linux stores them.</summary>
    public IReadOnlyList<string> Managed { get; set; } = Array.Empty<string>();

    /// <summary>Each asset that went in and its hash.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> Components { get; set; } = Array.Empty<KeyValuePair<string, string>>();

    /// <summary>Settings Panel changed in the game's own config under the user's profile, so removal can put them back.</summary>
    public IReadOnlyList<GameConfigRecord> GameConfig { get; set; } = Array.Empty<GameConfigRecord>();

    public int Files { get; set; }

    /// <summary>HelixSR's route inside its bridge; only the FSR drop-in exists.</summary>
    public string Way { get; set; } = "";

    /// <summary>Where HelixSR's bridge put its DLLs and record, which can differ from <see cref="Target"/>.</summary>
    public string ExeFolder { get; set; } = "";

    /// <summary>HelixSR's own log.</summary>
    public string Log { get; set; } = "";

    /// <summary>HelixSR's install record, the file whose presence says HelixSR is still in the game.</summary>
    public string HelixFile { get; set; } = "";
}

public sealed class OptiScalerInstallRequest
{
    public string Build { get; set; } = "";

    public string? Proxy { get; set; }

    public UpscalerChoice Choice { get; set; } = new();

    public bool ConfirmAntiCheat { get; set; }
}

/// <summary>
/// Installs an OptiScaler build into one game with the steps of the Linux backend's <c>install</c>: every asset is
/// downloaded and verified before the game is touched, the previous install comes out first, and the files go in
/// through <see cref="GameFiles"/> so they can be restored exactly. Checks that depend on Windows itself (game running,
/// Steam updating, protected folder) belong to the caller.
/// </summary>
public sealed class OptiScalerInstaller
{
    private const string DefaultProxy = "dxgi.dll";
    private readonly BuildCatalog _catalog;
    private readonly AssetCache _cache;
    private readonly string _gpu;
    private readonly string? _profile;
    private readonly string? _documents;

    /// <param name="profile">The user's profile folder, where a recipe's game settings live; the real one when omitted.</param>
    /// <param name="documents">The Documents folder for settings under <c>Documents/</c>; the real one (OneDrive included) when no profile is given, else <c>profile/Documents</c>.</param>
    public OptiScalerInstaller(BuildCatalog catalog, AssetCache cache, string gpu, string? profile = null, string? documents = null)
    {
        _catalog = catalog;
        _cache = cache;
        _gpu = gpu;
        _profile = profile ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        _documents = documents ?? (profile is null ? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) : null);
    }

    /// <param name="analyze">Reads the game folder; called again once the previous install is out.</param>
    /// <param name="claimed">Whether some other install of Panel's owns a folder.</param>
    /// <param name="automatic">The recipe's dependency packages and configuration, from <see cref="AutomaticRecipe.Plan"/>.</param>
    public async Task<InstalledUpscaler> InstallAsync(Func<GameAnalysis> analyze, ResolvedRecipe? recipe, OptiScalerInstallRequest request,
        InstalledUpscaler? previous, Func<string, bool> claimed, IProgress<long>? progress, CancellationToken cancel,
        AutomaticRecipe? automatic = null)
    {
        var build = _catalog.Build(request.Build);
        if (build is null || !build.Available)
        {
            throw new UpscalerException("unknown_build");
        }
        if (build.Engine != "optiscaler")
        {
            throw new UpscalerException("engine_unsupported", build.Engine);
        }
        if (request.Proxy is not null && !_catalog.Proxies.Contains(request.Proxy))
        {
            throw new UpscalerException("invalid_proxy");
        }
        var analysis = analyze();
        if (analysis.Target is null)
        {
            throw new UpscalerException("no_exe");
        }
        if (analysis.AntiCheat && !request.ConfirmAntiCheat)
        {
            throw new UpscalerException("anti_cheat");
        }
        var wantsAnr = request.Choice.FrameGen && request.Choice.FrameGenRoute == "anr";
        if (wantsAnr && !UpscalerPlanner.AnrCapable(_catalog, build, _gpu))
        {
            throw new UpscalerException("anr_build");
        }
        var target = analysis.Target;
        var effective = UpscalerPlanner.ForGame(_catalog, build, Inputs(analysis), _gpu, recipe?.Dependencies ?? Array.Empty<string>());
        RequestedFrameGen(analysis, recipe, effective, request.Choice, automatic is not null);

        // Everything is downloaded before the current install comes out: a failed or cancelled download leaves the
        // game exactly as it was.
        GameFiles.RecoverOrphan(target, claimed);
        var paths = await FetchAsync(Needed(effective, wantsAnr, recipe, automatic), progress, cancel).ConfigureAwait(false);
        if (wantsAnr)
        {
            AnrSources(paths[_catalog.AnrFrameGen], "");
        }
        automatic?.Sources(paths);
        if (previous is not null)
        {
            Uninstall(previous);
            // Files the game replaced since (an update) stayed behind with stale backups: those copies go, the game's stay.
            GameFiles.RecoverOrphan(target, _ => false);
            analysis = analyze();
            target = analysis.Target ?? throw new UpscalerException("no_exe");
        }
        if (analysis.Foreign)
        {
            throw new UpscalerException("foreign");
        }

        var proxy = request.Proxy ?? (recipe?.Proxy is { } named && _catalog.Proxies.Contains(named) ? named : null) ?? DefaultProxy;
        effective = UpscalerPlanner.ForGame(_catalog, build, Inputs(analysis), _gpu, recipe?.Dependencies ?? Array.Empty<string>());
        var assets = Needed(effective, wantsAnr, recipe, automatic);
        if (assets.Any(asset => !paths.ContainsKey(asset.Id)))
        {
            paths = await FetchAsync(assets, progress, cancel).ConfigureAwait(false);
        }
        var archive = _catalog.Asset(effective.Archive)!;
        var sources = OptiScalerRelease.Sources(paths[archive.Id], archive.Generation);
        if (!sources.TryGetValue(GameFiles.IniName, out var iniPath) || !sources.TryGetValue("OptiScaler.dll", out var injector))
        {
            throw new UpscalerException("unpack_failed", "release without OptiScaler.dll or OptiScaler.ini");
        }
        var baseIni = File.ReadAllText(iniPath, new UTF8Encoding(false, false));
        sources.Remove(GameFiles.IniName);
        sources.Remove("OptiScaler.dll");
        if (!string.IsNullOrEmpty(effective.Injector))
        {
            injector = paths[effective.Injector!];
        }
        var ordered = automatic is null ? new List<KeyValuePair<string, string>>() : automatic.Sources(paths).ToList();
        foreach (var pair in sources)
        {
            Put(ordered, pair.Key, pair.Value);
        }
        Put(ordered, proxy, injector);
        var prefix = string.IsNullOrEmpty(effective.ExtraDir) ? "" : effective.ExtraDir + "/";
        foreach (var pair in effective.Replace)
        {
            Put(ordered, prefix + pair.Key, paths[pair.Value]);
        }
        foreach (var id in effective.Assets)
        {
            Put(ordered, prefix + _catalog.Asset(id)!.FileName, paths[id]);
        }
        if (recipe is not null)
        {
            foreach (var pair in recipe.Files)
            {
                Put(ordered, pair.Key, paths[pair.Value]);
            }
            if (recipe.OptiPatcher && OptiPatcher() is { } optiPatcher)
            {
                Put(ordered, prefix + "plugins/OptiPatcher.asi", paths[optiPatcher.Id]);
            }
            foreach (var name in recipe.OptiScalerRootFiles)
            {
                var source = ordered.FirstOrDefault(pair => pair.Key == prefix + name);
                if (prefix.Length > 0 && source.Key is not null && !ordered.Any(pair => pair.Key == name))
                {
                    Put(ordered, name, source.Value);
                }
            }
        }

        if (wantsAnr)
        {
            foreach (var pair in AnrSources(paths[_catalog.AnrFrameGen], prefix))
            {
                Put(ordered, pair.Key, pair.Value);
            }
        }

        var frameGen = RequestedFrameGen(analysis, recipe, effective, request.Choice, automatic is not null);
        var panel = PanelIni.Compute(_catalog, effective, recipe?.Ini, recipe?.OptiPatcher == true, request.Choice, frameGen, previous?.Anr == true);
        var seeds = Path.Combine(_cache.Root, ".recipe-" + Guid.NewGuid().ToString("N"));
        GameManifest manifest;
        try
        {
            if (automatic is not null && automatic.Configuration.Count > 0)
            {
                Directory.CreateDirectory(seeds);
                foreach (var pair in automatic.ConfiguredSources(target, seeds))
                {
                    Put(ordered, pair.Key, pair.Value);
                }
            }
            if (recipe is not null && (recipe.Files.Values.Contains(ReframeworkConfig.Asset) || automatic?.PlacedFiles.Any(name => string.Equals(name, "dinput8.dll", StringComparison.OrdinalIgnoreCase)) == true))
            {
                Put(ordered, ReframeworkConfig.FileName, SeedReframework(target, seeds, recipe, request.Choice));
            }
            manifest = GameFiles.Apply(target, ordered, IniText.Apply(baseIni, panel), protect: recipe?.ProtectDlls == true,
                configuration: automatic?.Configuration);
        }
        finally
        {
            try
            {
                if (Directory.Exists(seeds))
                {
                    Directory.Delete(seeds, true);
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
        return new InstalledUpscaler
        {
            Build = effective.Id,
            Archive = effective.Archive,
            Proxy = proxy,
            Target = target,
            Exe = analysis.Exe,
            Options = Clean(request.Choice),
            FrameGenRoute = frameGen?.Route,
            Anr = wantsAnr,
            Args = recipe?.Args ?? Array.Empty<string>(),
            Managed = panel.Select(pair => pair.Key).OrderBy(key => key, StringComparer.Ordinal).ToList(),
            Components = assets.Select(asset => new KeyValuePair<string, string>(asset.Id, asset.Sha256)).ToList(),
            GameConfig = recipe is { GameConfig.Count: > 0 } ? GameConfigFiles.Apply(_profile, recipe.GameConfig, _documents).ToList() : Array.Empty<GameConfigRecord>(),
            Files = manifest.Files.Count,
        };
    }

    /// <summary>Takes an install out; returns the files kept because the game replaced them since.</summary>
    public static IReadOnlyList<string> Uninstall(InstalledUpscaler install)
    {
        var kept = GameFiles.Remove(install.Target);
        // Settings go back only once the files are out: a refused removal leaves both as they were.
        if (GameFiles.ReadManifest(install.Target) is null)
        {
            GameConfigFiles.Restore(install.GameConfig);
        }
        return kept;
    }

    /// <summary>REFramework's config with its menu closed (and its upscaler on Panel's quality), written beside the game's own.</summary>
    private static string SeedReframework(string target, string seeds, ResolvedRecipe recipe, UpscalerChoice choice)
    {
        var existing = Path.Combine(target, ReframeworkConfig.FileName);
        var current = "";
        try
        {
            var info = new FileInfo(existing);
            if (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0 && info.Length < ReframeworkConfig.MaximumBytes)
            {
                current = File.ReadAllText(existing, new UTF8Encoding(false, false));
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
        var values = ReframeworkConfig.Closed.Select(pair => new KeyValuePair<string, string?>(pair.Key, pair.Value)).ToList();
        if (recipe.ReframeworkUpscaler)
        {
            values.AddRange(ReframeworkConfig.Upscaler(choice.Quality));
        }
        Directory.CreateDirectory(seeds);
        var seed = Path.Combine(seeds, ReframeworkConfig.FileName);
        File.WriteAllText(seed, ReframeworkConfig.WithKeys(current, values), new UTF8Encoding(false));
        return seed;
    }

    private UpscalerAsset? OptiPatcher() =>
        _catalog.Archives.TryGetValue("optipatcher", out var id) ? _catalog.Asset(id) : null;

    private FrameGenPlan? RequestedFrameGen(GameAnalysis analysis, ResolvedRecipe? recipe, UpscalerBuild effective, UpscalerChoice choice,
        bool dependenciesReady)
    {
        var generation = _catalog.Asset(effective.Archive)!.Generation;
        var plan = SolutionPlan.Resolve(_catalog, _gpu, new PlanAnalysis { Apis = analysis.Apis, Inputs = Inputs(analysis), Streamline = analysis.Streamline },
            recipe is null ? null : new PlanRecipe
            {
                Args = recipe.Args,
                EffectiveApi = recipe.EffectiveApi,
                QualityOwner = recipe.QualityOwner,
                RecommendedInput = recipe.RecommendedInput,
                Dependencies = recipe.Dependencies,
            },
            generation, effective.Engine, choice.FrameGenRoute, dependenciesReady);
        var requested = SolutionPlan.RequestedFrameGen(plan, choice.FrameGen, choice.FrameGenRoute);
        if (choice.FrameGen && requested is null)
        {
            throw new UpscalerException("fg_route_unavailable");
        }
        return requested;
    }

    private IReadOnlyList<UpscalerAsset> Needed(UpscalerBuild build, bool anr, ResolvedRecipe? recipe, AutomaticRecipe? automatic)
    {
        var assets = UpscalerPlanner.BuildAssets(_catalog, build).ToList();
        foreach (var id in recipe?.Files.Values.Distinct(StringComparer.Ordinal) ?? Enumerable.Empty<string>())
        {
            var asset = _catalog.Asset(id) ?? throw new UpscalerException("recipe_unsupported", "unknown recipe asset " + id);
            if (!assets.Contains(asset))
            {
                assets.Add(asset);
            }
        }
        if (recipe?.OptiPatcher == true && OptiPatcher() is { } optiPatcher && !assets.Contains(optiPatcher))
        {
            assets.Add(optiPatcher);
        }
        if (anr && _catalog.Asset(_catalog.AnrFrameGen) is { } addOn && !assets.Contains(addOn))
        {
            assets.Add(addOn);
        }
        foreach (var asset in automatic?.Assets() ?? Array.Empty<UpscalerAsset>())
        {
            if (assets.All(known => known.Id != asset.Id))
            {
                assets.Add(asset);
            }
        }
        return assets;
    }

    /// <summary>ANR's provider folder as OptiScaler 10 finds it: <c>custom/&lt;provider&gt;/</c> next to OptiScaler.dll.</summary>
    private IReadOnlyList<KeyValuePair<string, string>> AnrSources(string unpacked, string prefix)
    {
        var root = Path.Combine(unpacked, _catalog.AnrProvider);
        if (!File.Exists(Path.Combine(root, "dlssg", "nvngx_dlssg.dll")))
        {
            throw new UpscalerException("anr_layout");
        }
        return Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .OrderBy(path => path, StringComparer.Ordinal)
            .Select(path => new KeyValuePair<string, string>(
                prefix + "custom/" + _catalog.AnrProvider + "/" + path.Substring(root.Length + 1).Replace(Path.DirectorySeparatorChar, '/'), path))
            .ToList();
    }

    private async Task<Dictionary<string, string>> FetchAsync(IReadOnlyList<UpscalerAsset> assets, IProgress<long>? progress, CancellationToken cancel)
    {
        var paths = new Dictionary<string, string>(StringComparer.Ordinal);
        var offset = 0L;
        foreach (var asset in assets)
        {
            var start = offset;
            var step = progress is null ? null : new Progress<long>(done => progress.Report(start + done));
            paths[asset.Id] = await _cache.EnsureAsync(asset, step, cancel).ConfigureAwait(false);
            offset += asset.Size;
        }
        return paths;
    }

    private UpscalerChoice Clean(UpscalerChoice choice) => new()
    {
        Quality = choice.Quality is not null && _catalog.QualityRatios.ContainsKey(choice.Quality) ? choice.Quality : null,
        Sharpness = choice.Sharpness is not null && _catalog.Sharpness.ContainsKey(choice.Sharpness) ? choice.Sharpness : null,
        FrameGen = choice.FrameGen,
        FrameGenRoute = choice.FrameGenRoute is "game" or "optiscaler" or "anr" ? choice.FrameGenRoute : null,
        Model = string.IsNullOrEmpty(choice.Model) ? null : choice.Model,
    };

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> Inputs(GameAnalysis analysis) =>
        analysis.Inputs.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);

    private static void Put(List<KeyValuePair<string, string>> sources, string relative, string path)
    {
        var index = sources.FindIndex(pair => GameManifest.PathComparer.Equals(pair.Key, relative));
        if (index >= 0)
        {
            sources[index] = new KeyValuePair<string, string>(relative, path);
        }
        else
        {
            sources.Add(new KeyValuePair<string, string>(relative, path));
        }
    }
}
