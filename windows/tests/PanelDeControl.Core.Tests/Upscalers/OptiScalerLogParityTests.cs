using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// The log reader must give the Linux backend's answers for every log of log_verdicts.json, which
/// tests/test_upscalers_log_parity.py writes from <c>logread.py</c>.
/// </summary>
public sealed class OptiScalerLogParityTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "log_verdicts.json")))!.AsObject();
    private readonly string _folder = Path.Combine(Path.GetTempPath(), "pdc-log-" + Guid.NewGuid().ToString("N"));

    public OptiScalerLogParityTests() => Directory.CreateDirectory(_folder);

    public void Dispose() => Directory.Delete(_folder, true);

    public static IEnumerable<object[]> Cases() =>
        Fixture["cases"]!.AsArray().Select(item => new object[] { item!["name"]!.GetValue<string>() });

    [Fact]
    public void FixtureHoldsEveryKindOfCase() => Assert.True(Fixture["cases"]!.AsArray().Count >= 50);

    [Theory]
    [MemberData(nameof(Cases))]
    public void ReadsLikeTheLinuxBackend(string name)
    {
        var fixture = Fixture["cases"]!.AsArray().Single(item => item!["name"]!.GetValue<string>() == name)!.AsObject();
        var expected = fixture["expected"]!.AsObject();
        var modified = DateTimeOffset.FromUnixTimeSeconds(Fixture["mtime"]!.GetValue<long>()).UtcDateTime;
        string? logText = fixture["log"] is JsonValue log ? log.GetValue<string>() : null;
        if (fixture["log_parts"] is JsonArray parts)
        {
            var builder = new StringBuilder();
            foreach (var part in parts)
            {
                var pair = part!.AsArray();
                builder.Insert(builder.Length, pair[0]!.GetValue<string>(), pair[1]!.GetValue<int>());
            }

            logText = builder.ToString();
        }

        if (logText is not null)
        {
            var path = Path.Combine(_folder, OptiScalerLog.LogName);
            File.WriteAllBytes(path, new UTF8Encoding(false).GetBytes(logText));
            File.SetLastWriteTimeUtc(path, modified);
        }

        DateTime? since = fixture["since"] is JsonValue seconds ? DateTimeOffset.FromUnixTimeSeconds(seconds.GetValue<long>()).UtcDateTime : null;
        var report = OptiScalerLog.Read(_folder, since);

        Assert.Equal(Canonical(expected["facts"]), Canonical(Facts(report)));
        Assert.Equal(expected["verdict"]!.GetValue<string>(), OptiScalerLog.Verdict(report));
        var provider = OptiScalerLog.ProviderObservationOf(report);
        Assert.Equal(Canonical(expected["provider_observation"]), Canonical(new JsonObject
        {
            ["provider_family"] = provider.Family,
            ["provider_name"] = provider.Name,
            ["provider_version"] = provider.Version,
            ["provider_model"] = provider.Model,
            ["provider_source"] = provider.Source,
            ["provider_confidence"] = provider.Confidence,
        }));

        var fallback = fixture["requested"] is JsonValue requested ? OptiScalerLog.FallbackOf("optiscaler", requested.GetValue<string>(), report) : null;
        Assert.Equal(Canonical(expected["fallback"]), Canonical(fallback is null ? null : new JsonObject
        {
            ["requested"] = fallback.Requested,
            ["observed"] = fallback.Observed,
            ["reason"] = fallback.Reason,
        }));

        bool? anr = null;
        if (fixture.ContainsKey("anr_log"))
        {
            var folder = Path.Combine(_folder, "dlssg");
            if (fixture["anr_log"] is JsonValue anrLog)
            {
                Directory.CreateDirectory(folder);
                var path = Path.Combine(folder, "nr_fg-1.log");
                File.WriteAllBytes(path, new UTF8Encoding(false).GetBytes(anrLog.GetValue<string>()));
                File.SetLastWriteTimeUtc(path, modified);
            }

            var after = fixture["anr_now_after"] is JsonValue offset ? offset.GetValue<int>() : 0;
            anr = OptiScalerLog.AnrGenerating(folder, modified.AddSeconds(after));
        }

        Assert.Equal(expected["anr_generating"]?.GetValue<bool>(), anr);
    }

    [Fact]
    public void ALogOfAnotherDayStartedTheDayBefore()
    {
        var path = Path.Combine(_folder, OptiScalerLog.LogName);
        File.WriteAllText(path, "[10:00:00.123456] [I] OptiScaler v0.9.4-final loaded\n");
        var noon = new DateTime(2026, 5, 20, 12, 0, 0, DateTimeKind.Local);
        File.SetLastWriteTime(path, noon);
        Assert.Equal(new DateTime(2026, 5, 20, 10, 0, 0, DateTimeKind.Local).ToUniversalTime(), OptiScalerLog.Read(_folder).Started);
        File.SetLastWriteTime(path, new DateTime(2026, 5, 20, 9, 0, 0, DateTimeKind.Local));
        Assert.Equal(new DateTime(2026, 5, 19, 10, 0, 0, DateTimeKind.Local).ToUniversalTime(), OptiScalerLog.Read(_folder).Started);
    }

    [Fact]
    public void TheLegacyFactsAgreeWithTheReport()
    {
        Assert.False(OptiScalerLogFacts.Read(_folder).Present);
        File.WriteAllText(Path.Combine(_folder, OptiScalerLog.LogName), "[I] NVSDK_NGX_D3D11_CreateFeature Creating new FSR 3.X w/Dx12 feature\n");
        var facts = OptiScalerLogFacts.Read(_folder);
        Assert.True(facts.Present);
        Assert.True(facts.UpscalerCreated);
    }

    private static JsonObject Facts(OptiScalerLogReport report)
    {
        var facts = new JsonObject { ["present"] = report.Present };
        if (!report.Present)
        {
            return facts;
        }

        if (report.Stale)
        {
            facts["stale"] = true;
            return facts;
        }

        Put(facts, "version", report.Version);
        Put(facts, "proxy", report.Proxy);
        Put(facts, "gpu", report.Gpu);
        Put(facts, "upscaler", report.Upscaler);
        Put(facts, "input", report.Input);
        Put(facts, "fg_state", report.FrameGenerationState);
        Put(facts, "fg_blind", report.FrameGenerationBlind);
        Put(facts, "fg", report.FrameGeneration);
        Put(facts, "fsr4_model", report.Fsr4Model);
        Put(facts, "fsr4_provider", report.Fsr4Provider);
        if (report.InitialResolution is { } resolution)
        {
            facts["initial_resolution"] = new JsonObject
            {
                ["render"] = new JsonArray(resolution.RenderWidth, resolution.RenderHeight),
                ["output"] = new JsonArray(resolution.OutputWidth, resolution.OutputHeight),
            };
        }

        if (report.TextureFailure)
        {
            facts["texture_failure"] = true;
        }

        facts["resolution_source"] = report.ResolutionSource;
        facts["errors"] = report.Errors;
        if (report.ErrorSources.Count > 0)
        {
            facts["error_sources"] = new JsonObject(report.ErrorSources.Select(pair => new KeyValuePair<string, JsonNode?>(pair.Key, pair.Value)));
        }

        return facts;
    }

    private static void Put(JsonObject facts, string key, string? value)
    {
        if (value is not null)
        {
            facts[key] = value;
        }
    }

    private static string Canonical(JsonNode? node) => node switch
    {
        null => "null",
        JsonObject item => "{" + string.Join(",", item.OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair => $"\"{pair.Key}\":{Canonical(pair.Value)}")) + "}",
        JsonArray list => "[" + string.Join(",", list.Select(Canonical)) + "]",
        _ => node.ToJsonString(),
    };
}
