using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class VcRuntimeProbeTests
{
    [Fact]
    public void ReadsTheVersionString()
    {
        var probe = Probe((VcRuntimeProbe.RuntimeKey, Values(("Installed", 1), ("Version", "v14.51.36247.00"))));

        Assert.Equal("14.51.36247.00", probe.InstalledVersion());
    }

    [Fact]
    public void FallsBackToTheNumericParts()
    {
        var probe = Probe((VcRuntimeProbe.RuntimeKeyWow64, Values(("Installed", 1), ("Major", 14), ("Minor", 40), ("Bld", 33810), ("Rbld", 0))));

        Assert.Equal("14.40.33810.0", probe.InstalledVersion());
    }

    [Fact]
    public void TakesTheNewestOfBothViews()
    {
        var probe = Probe(
            (VcRuntimeProbe.RuntimeKey, Values(("Installed", 1), ("Version", "v14.38.33135.00"))),
            (VcRuntimeProbe.RuntimeKeyWow64, Values(("Installed", 1), ("Version", "v14.44.35211.00"))));

        Assert.Equal("14.44.35211.00", probe.InstalledVersion());
    }

    [Fact]
    public void IgnoresKeysThatAreNotInstalledOrAbsent()
    {
        Assert.Null(Probe().InstalledVersion());
        Assert.Null(Probe((VcRuntimeProbe.RuntimeKey, Values(("Installed", 0), ("Version", "v14.51.36247.00")))).InstalledVersion());
    }

    [Fact]
    public void NeverThrows()
    {
        var probe = new VcRuntimeProbe(_ => throw new UnauthorizedAccessException());

        Assert.Null(probe.InstalledVersion());
    }

    [Fact]
    public void ReadsTheRealRegistryWithoutThrowing()
    {
        var version = new VcRuntimeProbe().InstalledVersion();

        Assert.True(version is null || version.Split('.').All(part => part.All(char.IsDigit)));
    }

    private static VcRuntimeProbe Probe(params (string Key, IReadOnlyDictionary<string, object?> Values)[] keys)
    {
        var map = keys.ToDictionary(pair => pair.Key, pair => pair.Values, StringComparer.Ordinal);
        return new VcRuntimeProbe(key => map.TryGetValue(key, out var values) ? values : null);
    }

    private static IReadOnlyDictionary<string, object?> Values(params (string Name, object Value)[] values) =>
        values.ToDictionary(pair => pair.Name, pair => (object?)pair.Value, StringComparer.Ordinal);
}
