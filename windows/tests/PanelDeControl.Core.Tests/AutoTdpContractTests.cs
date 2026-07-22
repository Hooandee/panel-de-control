using System.Text.Json;
using System.Text.Json.Serialization;
using PanelDeControl.Core.AutoTdp;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class AutoTdpContractTests
{
    [Fact]
    public void DecisionsMatchSharedContract()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Fixtures", "auto_tdp.json");
        var fixture = JsonSerializer.Deserialize<AutoTdpFixture>(File.ReadAllText(path));

        Assert.NotNull(fixture);
        foreach (var item in fixture.Cases)
        {
            var actual = AutoTdpController.Decide(
                item.Input.CurrentPl1,
                item.Input.GpuWindow,
                item.Input.SlackTicks,
                item.Input.MinWatts,
                item.Input.MaxWatts,
                item.Input.UpStep,
                item.Input.DownStep,
                item.Input.MaxDownStep);

            Assert.Equal(item.Expected.NextPl1, actual.NextPl1);
            Assert.Equal(item.Expected.SlackTicks, actual.SlackTicks);
        }
    }

    private sealed class AutoTdpFixture
    {
        [JsonPropertyName("cases")]
        public AutoTdpCase[] Cases { get; init; } = [];
    }

    private sealed class AutoTdpCase
    {
        [JsonPropertyName("input")]
        public AutoTdpInput Input { get; init; } = new();

        [JsonPropertyName("expected")]
        public AutoTdpExpected Expected { get; init; } = new();
    }

    private sealed class AutoTdpInput
    {
        [JsonPropertyName("current_pl1")]
        public int CurrentPl1 { get; init; }

        [JsonPropertyName("gpu_window")]
        public double?[] GpuWindow { get; init; } = [];

        [JsonPropertyName("slack_ticks")]
        public int SlackTicks { get; init; }

        [JsonPropertyName("min_w")]
        public int MinWatts { get; init; }

        [JsonPropertyName("max_w")]
        public int MaxWatts { get; init; }

        [JsonPropertyName("up_step")]
        public int UpStep { get; init; } = 2;

        [JsonPropertyName("down_step")]
        public int DownStep { get; init; } = 1;

        [JsonPropertyName("max_down_step")]
        public int MaxDownStep { get; init; } = 5;
    }

    private sealed class AutoTdpExpected
    {
        [JsonPropertyName("next_pl1")]
        public int NextPl1 { get; init; }

        [JsonPropertyName("slack_ticks")]
        public int SlackTicks { get; init; }
    }
}
