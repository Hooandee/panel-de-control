using PanelDeControl.Core.Telemetry;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class SensorPlausibilityTests
{
    [Theory]
    [InlineData(SensorKind.Temperature, 0.5, true)]
    [InlineData(SensorKind.Temperature, 125, true)]
    [InlineData(SensorKind.Temperature, 0, false)]
    [InlineData(SensorKind.Temperature, -1, false)]
    [InlineData(SensorKind.Temperature, 125.1, false)]
    [InlineData(SensorKind.Load, 0, true)]
    [InlineData(SensorKind.Load, 100, true)]
    [InlineData(SensorKind.Load, 100.5, false)]
    [InlineData(SensorKind.Load, -0.1, false)]
    [InlineData(SensorKind.Load, double.NaN, false)]
    [InlineData(SensorKind.Temperature, double.PositiveInfinity, false)]
    public void GatesReadingsByKind(SensorKind kind, double value, bool expected)
    {
        Assert.Equal(expected, SensorPlausibility.IsPlausible(kind, value));
    }

    [Fact]
    public void MissingValueIsNeverPlausible()
    {
        Assert.False(SensorPlausibility.IsPlausible(SensorKind.Load, null));
    }
}
