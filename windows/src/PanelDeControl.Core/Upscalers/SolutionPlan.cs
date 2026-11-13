namespace PanelDeControl.Core.Upscalers;

/// <summary>The recipe facts a solution plan reads, whether they come from a curated recipe or the wiki.</summary>
public sealed class PlanRecipe
{
    public IReadOnlyList<string> Args { get; set; } = Array.Empty<string>();
    public string? EffectiveApi { get; set; }
    public string QualityOwner { get; set; } = "panel";
    public string? RecommendedInput { get; set; }
    public IReadOnlyList<string> Dependencies { get; set; } = Array.Empty<string>();
    public RecipeFrameGen? FrameGen { get; set; }
    public bool OptiScalerFrameGen { get; set; } = true;
    public int? CatalogRevision { get; set; }
}

/// <summary>What game detection found that the plan needs.</summary>
public sealed class PlanAnalysis
{
    public IReadOnlyList<string> Apis { get; set; } = Array.Empty<string>();
    public IReadOnlyDictionary<string, IReadOnlyList<string>> Inputs { get; set; } = new Dictionary<string, IReadOnlyList<string>>();
    public int? Streamline { get; set; }
}

public sealed class SolutionPlanResult
{
    internal SolutionPlanResult()
    {
    }

    public bool InputReconciled { get; internal set; }
    public string? RecommendedInput { get; internal set; }
    public string? EffectiveApi { get; internal set; }
    /// <summary><c>recipe</c>, <c>detected</c> or <c>unknown</c>.</summary>
    public string ApiSource { get; internal set; } = "unknown";
    public string QualityOwner { get; internal set; } = "panel";
    public string? QualityReason { get; internal set; }
    public FrameGenPlan? FrameGenPlan { get; internal set; }
    public FrameGenPlan? OfferedFrameGenPlan { get; internal set; }
    public string? BlockedReason { get; internal set; }
    public string? WarningReason { get; internal set; }
    public IReadOnlyList<string> Dependencies { get; internal set; } = Array.Empty<string>();
    public int? RecipeRevision { get; internal set; }
}

/// <summary>
/// Capabilities of the composed game configuration, never evidence of execution: the same answers as
/// <c>py_modules/upscalers/solution_plan.py</c>.
/// </summary>
public static class SolutionPlan
{
    private static readonly Dictionary<string, string> ApiArguments = new(StringComparer.Ordinal)
    {
        ["-dx11"] = "d3d11",
        ["-d3d11"] = "d3d11",
        ["-dx12"] = "d3d12",
        ["-d3d12"] = "d3d12",
        ["-vulkan"] = "vulkan",
    };
    private static readonly HashSet<string> KnownApis = new(StringComparer.Ordinal) { "d3d11", "d3d12", "vulkan" };

    public static SolutionPlanResult Resolve(string gpu, PlanAnalysis analysis, PlanRecipe? recipe = null, int generation = 9,
        string engine = "optiscaler", string? route = null, bool dependenciesReady = false)
    {
        var forced = new HashSet<string>(StringComparer.Ordinal);
        foreach (var argument in recipe?.Args ?? Array.Empty<string>())
        {
            if (ApiArguments.TryGetValue(argument.ToLowerInvariant(), out var api))
            {
                forced.Add(api);
            }
        }
        if (!string.IsNullOrEmpty(recipe?.EffectiveApi))
        {
            forced.Add(recipe!.EffectiveApi!);
        }
        var detected = new HashSet<string>(analysis.Apis.Where(KnownApis.Contains), StringComparer.Ordinal);
        var conflict = forced.Count > 1;
        var effective = forced.Count == 1 ? forced.First() : forced.Count == 0 && detected.Count == 1 ? detected.First() : null;
        var optiscaler = engine == "optiscaler";
        var owner = optiscaler ? recipe?.QualityOwner ?? "panel" : "game";
        var recommended = recipe?.RecommendedInput;
        var offered = optiscaler
            ? UpscalerPlanner.FrameGenPlanFor(gpu, analysis.Inputs, recipe?.FrameGen, generation, new[] { "d3d12" }, analysis.Streamline, route)
            : null;
        FrameGenPlan? frameGen = null;
        if (optiscaler && !conflict)
        {
            frameGen = UpscalerPlanner.FrameGenPlanFor(gpu, analysis.Inputs, recipe?.FrameGen, generation, new[] { effective ?? "unknown" },
                analysis.Streamline, route);
            if (frameGen is not null && effective != "d3d12")
            {
                var routes = frameGen.Routes.Where(pair => pair.Key != "optiscaler" && pair.Value.Input is not ("fsrfg" or "xefg")).ToList();
                frameGen = routes.Count == 0 ? null
                    : new FrameGenPlan(route is not null && routes.Any(pair => pair.Key == route) ? route : routes[0].Key, routes);
            }
        }
        if (recipe is { OptiScalerFrameGen: false })
        {
            // OptiScaler's frame generation breaks this game: neither offered nor recommended (Mako and Lossless remain).
            frameGen = offered = null;
        }
        return new SolutionPlanResult
        {
            InputReconciled = optiscaler && dependenciesReady && !string.IsNullOrEmpty(recommended) && (recipe?.Dependencies.Count ?? 0) > 0,
            RecommendedInput = recommended,
            EffectiveApi = effective,
            ApiSource = forced.Count > 0 ? "recipe" : effective is not null ? "detected" : "unknown",
            QualityOwner = owner,
            QualityReason = owner == "game" ? "recipe_quality_game" : null,
            FrameGenPlan = frameGen,
            OfferedFrameGenPlan = offered,
            WarningReason = conflict ? "recipe_api_conflict" : null,
            Dependencies = optiscaler ? recipe?.Dependencies ?? Array.Empty<string>() : Array.Empty<string>(),
            RecipeRevision = recipe?.CatalogRevision,
        };
    }

    /// <summary>The frame generation the user's choice turns on, or null when it stays off.</summary>
    public static FrameGenPlan? RequestedFrameGen(SolutionPlanResult plan, bool frameGenOn, string? explicitRoute)
    {
        if (!frameGenOn)
        {
            return null;
        }
        var offered = plan.OfferedFrameGenPlan;
        if (string.IsNullOrEmpty(explicitRoute))
        {
            // Without a route of the user's own, a known non-DX12 game only gets one that works with its API.
            if (plan.FrameGenPlan is not null || plan.EffectiveApi is not (null or "d3d12"))
            {
                return plan.FrameGenPlan;
            }
            explicitRoute = offered?.Route;
        }
        return offered is not null && offered.Has(explicitRoute) ? UpscalerPlanner.FrameGenRoutePlan(offered, explicitRoute) : null;
    }
}
