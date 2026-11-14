namespace PanelDeControl.Core.Upscalers;

/// <summary>One frame generation path: what OptiScaler reads (<c>FGInput</c>) and what it produces (<c>FGOutput</c>).</summary>
public sealed class FrameGenRoute
{
    public FrameGenRoute(string input, string output, bool followsGame, string source, bool experimental)
    {
        Input = input;
        Output = output;
        FollowsGame = followsGame;
        Source = source;
        Experimental = experimental;
    }

    public string Input { get; }

    public string Output { get; }

    public bool FollowsGame { get; }

    /// <summary><c>game</c> for the game's own generator, <c>optiscaler</c> for OptiFG.</summary>
    public string Source { get; }

    public bool Experimental { get; }

    internal FrameGenRoute WithOutput(string output) => new(Input, output, FollowsGame, Source, Experimental);
}

/// <summary>The chosen route plus every route the game offers, in the order the Linux backend lists them.</summary>
public sealed class FrameGenPlan
{
    public FrameGenPlan(string route, IReadOnlyList<KeyValuePair<string, FrameGenRoute>> routes)
    {
        Route = route;
        Routes = routes;
        Selected = routes.First(pair => pair.Key == route).Value;
    }

    public string Route { get; }

    public FrameGenRoute Selected { get; }

    public IReadOnlyList<KeyValuePair<string, FrameGenRoute>> Routes { get; }

    public bool Has(string? route) => route is not null && Routes.Any(pair => pair.Key == route);
}

public sealed class BuildDescription
{
    internal BuildDescription()
    {
    }

    public string Id { get; internal set; } = "";
    public string Family { get; internal set; } = "";
    public string Version { get; internal set; } = "";
    public long Image { get; internal set; }
    public long Cost { get; internal set; }
    public bool Available { get; internal set; }
    public string Channel { get; internal set; } = "";
    public bool Supported { get; internal set; }
    public long DownloadBytes { get; internal set; }
    public IReadOnlyList<string> Models { get; internal set; } = Array.Empty<string>();
    public IReadOnlyList<string> DllNames { get; internal set; } = Array.Empty<string>();
    public IReadOnlyList<string> DllLegacyNames { get; internal set; } = Array.Empty<string>();
    public string Engine { get; internal set; } = "";
    public string? Way { get; internal set; }
    public string? MayFallback { get; internal set; }
}

/// <summary>
/// Which build a GPU gets, how a game reshapes it and which frame generation it can use: the same decisions as
/// <c>py_modules/upscalers/catalog.py</c>, checked against <c>shared/fixtures/upscalers/plan_parity.json</c>.
/// </summary>
public static class UpscalerPlanner
{
    // Device rules the Linux backend keeps in code next to the catalog.
    private static readonly HashSet<string> RdnaThreeIgpuDevices = new(StringComparer.Ordinal) { "rog_ally", "rog_ally_x", "legion_go", "legion_go_s" };
    private static readonly HashSet<string> SteamDecks = new(StringComparer.Ordinal) { "steam_deck_lcd", "steam_deck_oled" };
    // AMD's FP8 SDK providers ship their own FSR 3.1.6 and use it when the GPU can't run FP8 FSR 4 (seen on the Ally).
    private static readonly HashSet<string> Fp8Sdk = new(StringComparer.Ordinal) { "fsr-4.1.2-dll", "fsr-4.1.1-dll" };

    public static string PreferredBuild(BuildCatalog catalog, string gpu, string? recommendedBuild)
    {
        var recommended = recommendedBuild is null ? null : catalog.Build(recommendedBuild);
        if (recommended is { Available: true } && recommended.Gpus.Contains(gpu))
        {
            return recommended.Id;
        }
        return catalog.Preferred.TryGetValue(gpu, out var preferred) ? preferred : "fsr-3.1";
    }

    public static bool BuildSupported(UpscalerBuild build, string gpu, string device = "")
    {
        if (build.Id == "fsr-4.1.2-lite-igpu-dll")
        {
            return gpu == "rdna3" && RdnaThreeIgpuDevices.Contains(device);
        }
        if (build.Id == "fsr-4.1.2-dll" && SteamDecks.Contains(device))
        {
            return false;
        }
        return build.Gpus.Contains(gpu);
    }

    public static string? MayFallback(UpscalerBuild build, string gpu) => Fp8Sdk.Contains(build.Id) && gpu != "rdna4" ? "3.1.6" : null;

    public static IReadOnlyList<UpscalerAsset> BuildAssets(BuildCatalog catalog, UpscalerBuild build)
    {
        IEnumerable<string> ids = build.Engine switch
        {
            "dll" => build.Assets.Concat(build.Replace.Values).Concat(build.LegacyReplace.Values),
            "helixsr" => new[] { build.Archive },
            "proton" => Array.Empty<string>(),
            _ => new[] { build.Archive }.Concat(build.Assets).Concat(build.Replace.Values)
                .Concat(build.Injector is { Length: > 0 } injector ? new[] { injector } : Array.Empty<string>()),
        };
        return ids.Distinct(StringComparer.Ordinal).Select(id => catalog.Asset(id)!).ToList();
    }

    public static IReadOnlyList<BuildDescription> Describe(BuildCatalog catalog, string gpu, string device = "") =>
        catalog.Builds.Select(build => new BuildDescription
        {
            Id = build.Id,
            Family = build.Family,
            Version = build.Version,
            Image = build.Image,
            Cost = build.Cost,
            Available = build.Available,
            Channel = build.Channel,
            Supported = BuildSupported(build, gpu, device),
            DownloadBytes = build.Available
                ? BuildAssets(catalog, build).GroupBy(asset => asset.Sha256, StringComparer.Ordinal).Sum(group => group.Last().Size)
                : 0,
            Models = build.Models.Select(model => model.Id).ToList(),
            DllNames = build.Engine == "dll" ? build.Replace.Keys.ToList() : new List<string>(),
            DllLegacyNames = build.Engine == "dll" ? build.LegacyReplace.Keys.ToList() : new List<string>(),
            Engine = build.Engine,
            Way = build.Way.Length > 0 ? build.Way : null,
            MayFallback = MayFallback(build, gpu),
        }).ToList();

    public static IReadOnlyDictionary<string, string> ModelOverrides(UpscalerBuild? build, string? model)
    {
        if (build is null || build.Models.Count == 0)
        {
            return new Dictionary<string, string>();
        }
        var chosen = build.Models.FirstOrDefault(entry => entry.Id == model) ?? build.Models[0];
        return new Dictionary<string, string>(chosen.Ini.ToDictionary(pair => pair.Key, pair => pair.Value), StringComparer.Ordinal);
    }

    /// <summary>
    /// The build as this game needs it. OptiScaler 0.9 never sees FSR calls made through the FidelityFX SDK 2 loader,
    /// so XeSS, and FSR 3.1 away from AMD, move to OptiScaler 10 there; Luma's FSR 4.1.1 also needs 10.
    /// </summary>
    public static UpscalerBuild ForGame(BuildCatalog catalog, UpscalerBuild build, IReadOnlyDictionary<string, IReadOnlyList<string>> inputs,
        string gpu, IReadOnlyCollection<string> recipeDependencies)
    {
        var beta = catalog.Archives["optiscaler_beta"];
        if (build.Id == "fsr-4.1.1" && recipeDependencies.Any(dependency => dependency.StartsWith("luma-", StringComparison.Ordinal)))
        {
            return Reshaped(build, beta, "OptiScaler", new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["Upscalers.Dx12Upscaler"] = "ffx",
                ["Upscalers.Dx11Upscaler"] = "ffx_12",
                ["Upscalers.VulkanUpscaler"] = "ffx_12",
                ["FSR.Fsr4GpuSupport"] = "2",
                ["FSR.UpscalerIndex"] = "1",
            });
        }
        if (build.Archive != catalog.Archives["optiscaler"] || !(build.Id == "xess" || (build.Id == "fsr-3.1" && !catalog.Amd.Contains(gpu))))
        {
            return build;
        }
        var fsr31 = inputs.TryGetValue("fsr31", out var paths) ? paths : Array.Empty<string>();
        if (!fsr31.Any(path => FileName(path).ToLowerInvariant() == catalog.FfxLoader))
        {
            return build;
        }
        // The loader only hands the game's FSR to OptiScaler when OptiScaler offers an FSR 4 model it prefers.
        var ini = build.Ini.Where(pair => pair.Key != "FSR.Fsr4Update").ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        if (ini.TryGetValue("Upscalers.VulkanUpscaler", out var vulkan) && vulkan == "fsr31")
        {
            ini["Upscalers.VulkanUpscaler"] = "ffx";
        }
        ini["FSR.Fsr4GpuSupport"] = "4";
        return Reshaped(build, beta, "OptiScaler", ini);
    }

    /// <summary>
    /// Every frame generation path this game, GPU and OptiScaler generation can take. DLSSG via Streamline ranks
    /// first, then the game's FSR/Xe FG, then OptiFG; OptiFG and XeFG are DX12 only.
    /// </summary>
    public static IReadOnlyList<KeyValuePair<string, FrameGenRoute>> FrameGenRoutes(string gpu, IReadOnlyDictionary<string, IReadOnlyList<string>> inputs,
        IReadOnlyCollection<string> apis, int? streamline, int generation)
    {
        var output = gpu == "intel" ? "xefg" : "fsrfg";
        var dx12 = apis.Count == 0 || apis.Contains("d3d12");
        var candidates = new List<(string Input, string Output, bool FollowsGame)>();
        if (inputs.ContainsKey("dlssg"))
        {
            if (generation >= 10)
            {
                candidates.Add(("dlssg", output, (streamline ?? 0) >= 2));
            }
            else if ((streamline ?? 0) >= 2)
            {
                candidates.Add(("dlssg", output, false));
            }
            else
            {
                candidates.Add(("nukems", "nukems", false));
            }
        }
        var native = new List<(string Input, string Output, bool FollowsGame)>();
        if (inputs.ContainsKey("fsrfg") && dx12)
        {
            native.Add(("fsrfg", output, false));
        }
        if (inputs.ContainsKey("xefg") && dx12 && generation >= 10)
        {
            native.Insert(gpu == "intel" ? 0 : native.Count, ("xefg", output, false));
        }
        // Off NVIDIA, DLSSG only appears through spoofing the game may refuse; the game's own generator needs none.
        candidates = gpu != "nvidia" ? native.Concat(candidates).ToList() : candidates.Concat(native).ToList();
        var routes = new List<KeyValuePair<string, FrameGenRoute>>();
        if (candidates.Count > 0)
        {
            var game = candidates[0];
            if (output == "xefg" && !dx12)
            {
                game.Output = "fsrfg";
            }
            routes.Add(new("game", new FrameGenRoute(game.Input, game.Output, game.FollowsGame, "game", false)));
        }
        if (dx12)
        {
            routes.Add(new("optiscaler", new FrameGenRoute("upscaler", output, false, "optiscaler", true)));
        }
        return routes;
    }

    public static FrameGenPlan? FrameGenPlanFor(string gpu, IReadOnlyDictionary<string, IReadOnlyList<string>> inputs, RecipeFrameGen? recipeFrameGen,
        int generation, IReadOnlyCollection<string> apis, int? streamline, string? route)
    {
        var routes = FrameGenRoutes(gpu, inputs, apis, streamline, generation).ToList();
        if (recipeFrameGen is not null && generation == 9)
        {
            var game = new FrameGenRoute(recipeFrameGen.Input, recipeFrameGen.Output ?? "fsrfg", false, "game", false);
            var at = routes.FindIndex(pair => pair.Key == "game");
            if (at >= 0)
            {
                routes[at] = new("game", game);
            }
            else
            {
                routes.Add(new("game", game));
            }
        }
        if (routes.Count == 0)
        {
            return null;
        }
        var name = route is not null && routes.Any(pair => pair.Key == route) ? route
            : routes.Any(pair => pair.Key == "game") ? "game" : "optiscaler";
        return new FrameGenPlan(name, routes);
    }

    /// <summary>The stored plan switched to another of its routes, without re-scanning the game.</summary>
    public static FrameGenPlan? FrameGenRoutePlan(FrameGenPlan? plan, string? route) =>
        plan is null || !plan.Has(route) ? plan : new FrameGenPlan(route!, plan.Routes);

    public static IReadOnlyDictionary<string, string> FrameGenOverrides(FrameGenPlan? plan, bool enabled)
    {
        if (!enabled || plan is null)
        {
            return new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["FrameGen.Enabled"] = "false",
                ["FrameGen.FGInput"] = "nofg",
                ["FrameGen.FGOutput"] = "nofg",
            };
        }
        var overrides = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["FrameGen.Enabled"] = plan.Selected.FollowsGame ? "auto" : "true",
            ["FrameGen.FGInput"] = plan.Selected.Input,
            ["FrameGen.FGOutput"] = plan.Selected.Output,
        };
        if (plan.Selected.Input == "upscaler")
        {
            overrides["OptiFG.HUDFix"] = "true";
        }
        return overrides;
    }

    private static string FileName(string path)
    {
        var slash = path.LastIndexOf('/');
        return slash >= 0 ? path.Substring(slash + 1) : path;
    }

    private static UpscalerBuild Reshaped(UpscalerBuild build, string archive, string extraDir, IReadOnlyDictionary<string, string> ini) => new()
    {
        Id = build.Id,
        Family = build.Family,
        Version = build.Version,
        Gpus = build.Gpus,
        Image = build.Image,
        Cost = build.Cost,
        Assets = build.Assets,
        Replace = build.Replace,
        Ini = ini,
        Injector = build.Injector,
        Available = build.Available,
        Archive = archive,
        Channel = build.Channel,
        ExtraDir = extraDir,
        Models = build.Models,
        Engine = build.Engine,
        Way = build.Way,
        LegacyReplace = build.LegacyReplace,
    };
}

/// <summary>A recipe's own frame generation, as the curated recipe or the wiki states it.</summary>
public sealed class RecipeFrameGen
{
    public RecipeFrameGen(string input, string? output = null)
    {
        Input = input;
        Output = output;
    }

    public string Input { get; }

    public string? Output { get; }
}
