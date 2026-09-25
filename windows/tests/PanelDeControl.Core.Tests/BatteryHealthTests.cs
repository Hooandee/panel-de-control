using PanelDeControl.Core.Telemetry;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class BatteryHealthTests
{
    [Fact]
    public void HealthIsTheFullChargeShareOfTheDesignCapacity()
    {
        var readings = BatteryHealth.Map(new BatteryHealthSample(80_000, 72_000, 143), "wmi");

        Assert.Equal(90, Value(readings, BatteryHealth.HealthId));
        Assert.Equal(143, Value(readings, BatteryHealth.CyclesId));
        Assert.Equal(80_000, Value(readings, BatteryHealth.DesignCapacityId));
    }

    [Theory]
    [InlineData(0u)]
    [InlineData(uint.MaxValue)]
    public void UnreportedCapacityNeverBecomesAHealthValue(uint design)
    {
        var readings = BatteryHealth.Map(new BatteryHealthSample(design, 72_000, 10), "wmi");

        Assert.Equal(ReadingStatus.Unavailable, Reading(readings, BatteryHealth.HealthId).Status);
        Assert.Equal(ReadingStatus.Unavailable, Reading(readings, BatteryHealth.DesignCapacityId).Status);
    }

    [Fact]
    public void ZeroCyclesIsTreatedAsUnreported()
    {
        var readings = BatteryHealth.Map(new BatteryHealthSample(80_000, 79_000, 0), "wmi");

        Assert.Equal("battery_health_unreported", Reading(readings, BatteryHealth.CyclesId).ErrorCode);
    }

    private static TelemetryReading Reading(IReadOnlyList<TelemetryReading> readings, string id) =>
        readings.Single(reading => reading.Id == id);

    private static double? Value(IReadOnlyList<TelemetryReading> readings, string id) => Reading(readings, id).Value;
}
