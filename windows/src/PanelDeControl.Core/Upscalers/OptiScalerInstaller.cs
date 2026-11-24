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

    public int Files { get; set; }
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

    public OptiScalerInstaller(BuildCatalog catalog, AssetCache cache, string gpu)
    {
        _catalog = catalog;
        _cache = cache;
        _gpu = gpu;
    }

    /// <param name="analyze">Reads the game folder; called again once the previous install is out.</param>
    /// <param name="claimed">Whether some other install of Panel's owns a folder.</param>
    public async Task<InstalledUpscaler> InstallAsync(Func<GameAnalysis> analyze, GameRecipe? recipe, OptiScalerInstallRequest request,
        InstalledUpscaler? previous, Func<string, bool> claimed, IProgress<long>? progress, CancellationToken cancel)
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
        if (recipe is not null && (recipe.Dependencies.Count > 0 || recipe.Configuration.Count > 0))
        {
            throw new UpscalerException("recipe_unsupported", "recipe dependencies are not installed on Windows yet");
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
        RequestedFrameGen(analysis, recipe, effective, request.Choice);

        // Everything is downloaded before the current install comes out: a failed or cancelled download leaves the
        // game exactly as it was.
        GameFiles.RecoverOrphan(target, claimed);
        var paths = await FetchAsync(Needed(effective, wantsAnr), progress, cancel).ConfigureAwait(false);
        if (wantsAnr)
        {
            AnrSources(paths[_catalog.AnrFrameGen], "");
        }
        if (previous is not null)
        {
            GameFiles.Remove(previous.Target);
            // Files the game replaced since (an update) stayed behind with stale backups: those copies go, the game's stay.
            GameFiles.RecoverOrphan(target, _ => false);
            analysis = analyze();
            target = analysis.Target ?? throw new UpscalerException("no_exe");
        }
        if (analysis.Foreign)
        {
            throw new UpscalerException("foreign");
        }

        var proxy = request.Proxy ?? DefaultProxy;
        effective = UpscalerPlanner.ForGame(_catalog, build, Inputs(analysis), _gpu, recipe?.Dependencies ?? Array.Empty<string>());
        var assets = Needed(effective, wantsAnr);
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
        var ordered = sources.ToList();
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

        var frameGen = RequestedFrameGen(analysis, recipe, effective, request.Choice);
        var panel = PanelIni.Compute(_catalog, effective, recipe?.Ini, false, request.Choice, frameGen, previous?.Anr == true);
        var manifest = GameFiles.Apply(target, ordered, IniText.Apply(baseIni, panel));
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
            Files = manifest.Files.Count,
        };
    }

    /// <summary>Takes an install out; returns the files kept because the game replaced them since.</summary>
    public static IReadOnlyList<string> Uninstall(InstalledUpscaler install) => GameFiles.Remove(install.Target);

    private FrameGenPlan? RequestedFrameGen(GameAnalysis analysis, GameRecipe? recipe, UpscalerBuild effective, UpscalerChoice choice)
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
            generation, effective.Engine, choice.FrameGenRoute);
        var requested = SolutionPlan.RequestedFrameGen(plan, choice.FrameGen, choice.FrameGenRoute);
        if (choice.FrameGen && requested is null)
        {
            throw new UpscalerException("fg_route_unavailable");
        }
        return requested;
    }

    private IReadOnlyList<UpscalerAsset> Needed(UpscalerBuild build, bool anr)
    {
        var assets = UpscalerPlanner.BuildAssets(_catalog, build).ToList();
        if (anr && _catalog.Asset(_catalog.AnrFrameGen) is { } addOn && !assets.Contains(addOn))
        {
            assets.Add(addOn);
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
        var index = sources.FindIndex(pair => pair.Key == relative);
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
