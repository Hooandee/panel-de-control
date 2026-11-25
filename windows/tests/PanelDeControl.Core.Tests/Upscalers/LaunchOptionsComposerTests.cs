using System.Text.Json;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class LaunchOptionsComposerTests
{
    public static IEnumerable<object[]> Cases()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "launch_options.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        foreach (var item in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            yield return [item.GetProperty("id").GetString()!, item.GetRawText()];
        }
    }

    [Theory]
    [MemberData(nameof(Cases))]
    public void MatchesTheTypeScriptComposer(string id, string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        var input = root.GetProperty("input");
        var expected = root.GetProperty("expected");
        var launch = input.GetProperty("launch").GetString()!;

        LaunchOptionsPlan? actual = root.GetProperty("op").GetString() switch
        {
            "apply" => LaunchOptionsComposer.Apply(launch, Strings(input, "args")),
            "revert" => LaunchOptionsComposer.Revert(launch, Strings(input, "added")) is { } value ? new LaunchOptionsPlan(value, []) : null,
            "replace" => LaunchOptionsComposer.Replace(launch, Strings(input, "removed"), Strings(input, "args")),
            var op => throw new InvalidOperationException($"unknown op {op} in {id}"),
        };

        if (expected.ValueKind == JsonValueKind.Null)
        {
            Assert.Null(actual);
            return;
        }

        Assert.NotNull(actual);
        Assert.Equal(expected.GetProperty("value").GetString(), actual.Value);
        if (expected.TryGetProperty("added", out var added))
        {
            Assert.Equal(added.EnumerateArray().Select(entry => entry.GetString()), actual.Added);
        }
    }

    private static string[] Strings(JsonElement parent, string name) =>
        parent.GetProperty(name).EnumerateArray().Select(entry => entry.GetString()!).ToArray();
}
