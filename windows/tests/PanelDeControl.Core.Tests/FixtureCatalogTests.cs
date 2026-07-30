using System.Text.Json;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class FixtureCatalogTests
{
    private static readonly HashSet<string> ExpectedFiles = new(StringComparer.Ordinal)
    {
        "auto_tdp.json",
        "fan_suggestions.json",
        "tdp_learned_band.json",
        "telemetry_learning.json",
    };

    [Fact]
    public void SharedFixtureCatalogIsCompleteAndVersioned()
    {
        var fixtureDirectory = Path.Combine(AppContext.BaseDirectory, "Fixtures");
        var files = Directory.GetFiles(fixtureDirectory, "*.json")
            .Select(Path.GetFileName)
            .Where(name => name is not null)
            .Cast<string>()
            .ToHashSet(StringComparer.Ordinal);

        Assert.True(ExpectedFiles.SetEquals(files));
        foreach (var path in Directory.GetFiles(fixtureDirectory, "*.json"))
        {
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            var root = document.RootElement;
            Assert.Equal(1, root.GetProperty("schema_version").GetInt32());
            Assert.False(string.IsNullOrWhiteSpace(root.GetProperty("algorithm").GetString()));
            Assert.NotEmpty(root.GetProperty("cases").EnumerateArray());
        }
    }
}
