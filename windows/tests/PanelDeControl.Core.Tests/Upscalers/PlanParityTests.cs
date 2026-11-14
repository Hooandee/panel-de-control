using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// Version choice, frame generation and the solution plan must give the Linux backend's answers for every case in
/// plan_parity.json, which tests/test_upscalers_plan_parity.py writes.
/// </summary>
public sealed class PlanParityTests
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "plan_parity.json")))!.AsObject();
    private static readonly BuildCatalog Catalog = BuildCatalog.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "catalog.json")));

    [Fact]
    public void DescribeMatches() => Check("describe", (key, parts) =>
        new JsonArray(UpscalerPlanner.Describe(Catalog, parts[0], parts[1]).Select(Describe).ToArray()));

    [Fact]
    public void PreferredBuildMatches()
    {
        foreach (var pair in Fixture["preferred"]!.AsObject())
        {
            var parts = pair.Key.Split('|');
            Assert.Equal(pair.Value!.GetValue<string>(), UpscalerPlanner.PreferredBuild(Catalog, parts[0], parts[1].Length == 0 ? null : parts[1]));
        }
    }

    [Fact]
    public void ForGameMatches() => Check("for_game", (key, parts) =>
    {
        var build = UpscalerPlanner.ForGame(Catalog, Catalog.Build(parts[0])!, Inputs(parts[1]), parts[2],
            parts[3] == "luma" ? new[] { "luma-ff7" } : Array.Empty<string>());
        return new JsonObject { ["archive"] = build.Archive, ["extra_dir"] = build.ExtraDir, ["ini"] = Map(build.Ini) };
    });

    [Fact]
    public void ModelOverridesMatch()
    {
        foreach (var pair in Fixture["models"]!.AsObject())
        {
            var parts = pair.Key.Split('|');
            AssertSame(pair.Key, pair.Value, Map(UpscalerPlanner.ModelOverrides(Catalog.Build(parts[0]), parts[1].Length == 0 ? null : parts[1])));
        }
    }

    [Fact]
    public void FrameGenRoutesMatch() => Check("fg_routes", (key, parts) =>
        Routes(UpscalerPlanner.FrameGenRoutes(parts[0], Inputs(parts[1]), Apis(parts[2]), Streamline(parts[3]), int.Parse(parts[4], CultureInfo.InvariantCulture))));

    [Fact]
    public void FrameGenPlansMatch() => Check("fg_plans", (key, parts) =>
    {
        var plan = UpscalerPlanner.FrameGenPlanFor(parts[0], Inputs(parts[1]), parts[3].Length == 0 ? null : new RecipeFrameGen(parts[3]),
            int.Parse(parts[4], CultureInfo.InvariantCulture), Apis(parts[2]), 2, parts[5].Length == 0 ? null : parts[5]);
        return new JsonObject
        {
            ["plan"] = Plan(plan),
            ["overrides_on"] = Map(UpscalerPlanner.FrameGenOverrides(plan, true)),
            ["overrides_off"] = Map(UpscalerPlanner.FrameGenOverrides(plan, false)),
            ["switched"] = Plan(UpscalerPlanner.FrameGenRoutePlan(plan, "optiscaler")),
        };
    });

    [Fact]
    public void SolutionPlansMatch() => Check("solutions", (key, parts) =>
    {
        var route = parts[5].Length == 0 ? null : parts[5];
        var plan = SolutionPlan.Resolve(parts[0], Analysis(parts[2]), Recipe(parts[1]), int.Parse(parts[3], CultureInfo.InvariantCulture),
            parts[4], route, parts[6] == "1");
        return new JsonObject
        {
            ["plan"] = Describe(plan),
            ["requested"] = new JsonObject
            {
                ["on"] = Plan(SolutionPlan.RequestedFrameGen(plan, true, route)),
                ["off"] = Plan(SolutionPlan.RequestedFrameGen(plan, false, route)),
            },
        };
    });

    private static void Check(string section, Func<string, string[], JsonNode?> answer)
    {
        var table = Fixture[section]!.AsObject();
        var values = table["values"]!.AsArray();
        var failures = new List<string>();
        foreach (var pair in table["cases"]!.AsObject())
        {
            var expected = values[pair.Value!.GetValue<int>()];
            var actual = answer(pair.Key, pair.Key.Split('|'));
            if (!Same(expected, actual))
            {
                failures.Add($"{pair.Key}\n  expected {expected?.ToJsonString()}\n  got      {actual?.ToJsonString()}");
            }
        }
        Assert.True(failures.Count == 0, $"{failures.Count} of {table["cases"]!.AsObject().Count} cases differ:\n" + string.Join("\n", failures.Take(5)));
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> Inputs(string name) =>
        Fixture["input_sets"]![name]!.AsObject().ToDictionary(pair => pair.Key, pair => (IReadOnlyList<string>)Strings(pair.Value).ToList());

    private static IReadOnlyCollection<string> Apis(string index) => Strings(Fixture["api_sets"]![int.Parse(index, CultureInfo.InvariantCulture)]).ToList();

    private static int? Streamline(string text) => text == "None" ? null : int.Parse(text, CultureInfo.InvariantCulture);

    private static PlanAnalysis Analysis(string name)
    {
        var node = Fixture["analyses"]![name]!;
        return new PlanAnalysis
        {
            Apis = Strings(node["apis"]).ToList(),
            Inputs = node["inputs"]!.AsObject().ToDictionary(pair => pair.Key, pair => (IReadOnlyList<string>)Strings(pair.Value).ToList()),
            Streamline = node["streamline"]?.GetValue<int>(),
        };
    }

    private static PlanRecipe? Recipe(string name)
    {
        var node = Fixture["recipes"]![name];
        if (node is null)
        {
            return null;
        }
        var fg = node["fg"];
        return new PlanRecipe
        {
            Args = Strings(node["args"]).ToList(),
            EffectiveApi = node["effective_api"]?.GetValue<string>(),
            QualityOwner = node["quality_owner"]!.GetValue<string>(),
            RecommendedInput = node["recommended_input"]?.GetValue<string>(),
            Dependencies = Strings(node["dependencies"]).ToList(),
            FrameGen = fg is null ? null : new RecipeFrameGen(fg["input"]!.GetValue<string>(), fg["output"]?.GetValue<string>()),
            OptiScalerFrameGen = node["optiscaler_fg"]!.GetValue<bool>(),
            CatalogRevision = node["catalog_revision"]?.GetValue<int>(),
        };
    }

    private static JsonNode Describe(BuildDescription build) => new JsonObject
    {
        ["id"] = build.Id, ["family"] = build.Family, ["version"] = build.Version, ["image"] = build.Image, ["cost"] = build.Cost,
        ["available"] = build.Available, ["channel"] = build.Channel, ["supported"] = build.Supported, ["download_bytes"] = build.DownloadBytes,
        ["models"] = List(build.Models), ["dll_names"] = List(build.DllNames), ["dll_legacy_names"] = List(build.DllLegacyNames),
        ["engine"] = build.Engine, ["way"] = build.Way, ["may_fallback"] = build.MayFallback,
    };

    private static JsonNode Describe(SolutionPlanResult plan) => new JsonObject
    {
        ["input_reconciled"] = plan.InputReconciled, ["recommended_input"] = plan.RecommendedInput, ["effective_api"] = plan.EffectiveApi,
        ["api_source"] = plan.ApiSource, ["quality"] = new JsonObject { ["owner"] = plan.QualityOwner, ["reason"] = plan.QualityReason },
        ["fg_plan"] = Plan(plan.FrameGenPlan), ["offered_fg_plan"] = Plan(plan.OfferedFrameGenPlan), ["blocked_reason"] = plan.BlockedReason,
        ["warning_reason"] = plan.WarningReason, ["dependencies"] = List(plan.Dependencies), ["recipe_revision"] = plan.RecipeRevision,
    };

    private static JsonObject Route(FrameGenRoute route) => new()
    {
        ["input"] = route.Input, ["output"] = route.Output, ["follows_game"] = route.FollowsGame,
        ["source"] = route.Source, ["experimental"] = route.Experimental,
    };

    private static JsonObject Routes(IEnumerable<KeyValuePair<string, FrameGenRoute>> routes) =>
        new(routes.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, Route(pair.Value))));

    private static JsonNode? Plan(FrameGenPlan? plan)
    {
        if (plan is null)
        {
            return null;
        }
        var node = Route(plan.Selected);
        node["route"] = plan.Route;
        node["routes"] = Routes(plan.Routes);
        return node;
    }

    private static JsonObject Map(IEnumerable<KeyValuePair<string, string>> pairs) =>
        new(pairs.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value)));

    private static JsonArray List(IEnumerable<string> items) => new(items.Select(item => (JsonNode?)item).ToArray());

    private static IEnumerable<string> Strings(JsonNode? node) => node!.AsArray().Select(item => item!.GetValue<string>());

    private static void AssertSame(string key, JsonNode? expected, JsonNode? actual) =>
        Assert.True(Same(expected, actual), $"{key}: expected {expected?.ToJsonString()} but got {actual?.ToJsonString()}");

    private static bool Same(JsonNode? expected, JsonNode? actual) => (expected, actual) switch
    {
        (null, null) => true,
        (JsonObject left, JsonObject right) => left.Count == right.Count && left.All(pair => right.ContainsKey(pair.Key) && Same(pair.Value, right[pair.Key])),
        (JsonArray left, JsonArray right) => left.Count == right.Count && left.Zip(right, Same).All(same => same),
        (JsonValue left, JsonValue right) when left.GetValueKind() == JsonValueKind.Number && right.GetValueKind() == JsonValueKind.Number =>
            double.Parse(left.ToJsonString(), CultureInfo.InvariantCulture) == double.Parse(right.ToJsonString(), CultureInfo.InvariantCulture),
        (JsonValue left, JsonValue right) => JsonNode.DeepEquals(left, right),
        _ => false,
    };
}
