using PanelDeControl.Core.Telemetry;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class SensorSelectorTests
{
    [Fact]
    public void PreferredExactNameWinsOverDiscoveryOrder()
    {
        var candidates = new[]
        {
            Candidate("cpu/temp/edge", "Core", 71),
            Candidate("cpu/temp/package", "CPU Package", 74),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Cpu,
            SensorKind.Temperature,
            new[] { "CPU Package", "Core" });

        Assert.NotNull(selected);
        Assert.Equal("cpu/temp/package", selected.Identifier);
        Assert.Equal(74, selected.Value);
    }

    [Fact]
    public void InvalidPreferredTemperatureFallsBackToPlausibleCandidate()
    {
        var candidates = new[]
        {
            Candidate("cpu/temp/package", "CPU Package", 255),
            Candidate("cpu/temp/core", "Core", 69),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Cpu,
            SensorKind.Temperature,
            new[] { "CPU Package", "Core" });

        Assert.NotNull(selected);
        Assert.Equal("cpu/temp/core", selected.Identifier);
    }

    [Fact]
    public void MissingAndNonFiniteValuesAreNeverSelected()
    {
        var candidates = new[]
        {
            Candidate("gpu/load/missing", "GPU Core", null, HardwareKind.Gpu, SensorKind.Load),
            Candidate("gpu/load/nan", "GPU Total", double.NaN, HardwareKind.Gpu, SensorKind.Load),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Gpu,
            SensorKind.Load,
            new[] { "GPU Core", "GPU Total" });

        Assert.Null(selected);
    }

    [Fact]
    public void ZeroLoadIsAValidReading()
    {
        var candidates = new[]
        {
            Candidate("gpu/load/core", "GPU Core", 0, HardwareKind.Gpu, SensorKind.Load),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Gpu,
            SensorKind.Load,
            new[] { "GPU Core" });

        Assert.NotNull(selected);
        Assert.Equal(0, selected.Value);
    }

    [Fact]
    public void UnknownSensorNamesAreNotSelected()
    {
        var candidates = new[]
        {
            Candidate("cpu/temp/z", "Other", 70),
            Candidate("cpu/temp/a", "Other", 72),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Cpu,
            SensorKind.Temperature,
            new[] { "CPU Package", "Core" });

        Assert.Null(selected);
    }

    [Fact]
    public void DuplicateKnownNamesUseStableIdentifierOrdering()
    {
        var candidates = new[]
        {
            Candidate("cpu/temp/z", "CPU Package", 70),
            Candidate("cpu/temp/a", "CPU Package", 72),
        };

        var selected = SensorSelector.Select(
            candidates,
            HardwareKind.Cpu,
            SensorKind.Temperature,
            new[] { "CPU Package" });

        Assert.NotNull(selected);
        Assert.Equal("cpu/temp/a", selected.Identifier);
    }

    private static SensorCandidate Candidate(
        string identifier,
        string name,
        double? value,
        HardwareKind hardwareKind = HardwareKind.Cpu,
        SensorKind sensorKind = SensorKind.Temperature)
    {
        return new SensorCandidate(
            identifier,
            hardwareKind,
            sensorKind,
            name,
            value,
            identifier);
    }
}
