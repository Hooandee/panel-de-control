using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class PowerStatusReaderTests
{
    [Fact]
    public void EmptyBatteryIsStillAnAvailableZero()
    {
        var readings = PowerStatusReader.Map(
            new NativePowerStatus(AcLineStatus: 0, BatteryLifePercent: 0));

        var battery = Assert.Single(readings, reading => reading.Id == "battery.level");
        Assert.Equal(ReadingStatus.Available, battery.Status);
        Assert.Equal(0, battery.Value);
    }

    [Fact]
    public void WindowsUnknownSentinelDoesNotBecomeAValue()
    {
        var readings = PowerStatusReader.Map(
            new NativePowerStatus(AcLineStatus: 255, BatteryLifePercent: 255));

        Assert.All(readings, reading =>
        {
            Assert.Equal(ReadingStatus.Unavailable, reading.Status);
            Assert.Null(reading.Value);
            Assert.Equal("power_state_unknown", reading.ErrorCode);
        });
    }

    [Fact]
    public void OutOfRangeBatteryPercentageDoesNotBecomeAReading()
    {
        var readings = PowerStatusReader.Map(
            new NativePowerStatus(AcLineStatus: 1, BatteryLifePercent: 101));

        var battery = Assert.Single(readings, reading => reading.Id == "battery.level");
        Assert.Equal(ReadingStatus.Unavailable, battery.Status);
        Assert.Null(battery.Value);
        Assert.Equal("power_state_unknown", battery.ErrorCode);
    }
}
