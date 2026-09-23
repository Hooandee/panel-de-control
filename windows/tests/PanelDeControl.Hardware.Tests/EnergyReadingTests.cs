using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class EnergyReadingTests
{
    [Fact]
    public void DischargingBatteryGivesSystemDrawAndTimeLeft()
    {
        var readings = PowerStatusReader.MapEnergy(new NativeBatteryState(true, false, true, -4144, 18952));

        Assert.Equal(4.1, Reading(readings, "power.draw").Value);
        Assert.Equal(316, Reading(readings, "battery.time_remaining").Value);
    }

    [Fact]
    public void OnTheChargerTheDrawIsNotMeasured()
    {
        var readings = PowerStatusReader.MapEnergy(new NativeBatteryState(true, true, false, 25000, uint.MaxValue));

        var draw = Reading(readings, "power.draw");
        Assert.Null(draw.Value);
        Assert.Equal("power_draw_on_ac", draw.ErrorCode);
        Assert.Equal("time_remaining_unknown", Reading(readings, "battery.time_remaining").ErrorCode);
    }

    [Fact]
    public void ZeroRateWhileDischargingIsPendingNotZeroWatts()
    {
        var draw = Reading(PowerStatusReader.MapEnergy(new NativeBatteryState(true, false, true, 0, 0)), "power.draw");

        Assert.Null(draw.Value);
        Assert.Equal("power_draw_pending", draw.ErrorCode);
    }

    [Fact]
    public void NoBatteryOrFailedQueryIsUnavailable()
    {
        Assert.All(PowerStatusReader.MapEnergy(null), reading => Assert.Equal(ReadingStatus.Unavailable, reading.Status));
        Assert.All(
            PowerStatusReader.MapEnergy(new NativeBatteryState(false, false, false, 0, 0)),
            reading => Assert.Equal("battery_state_unavailable", reading.ErrorCode));
    }

    [Fact]
    public void PowerModesMapTheWindowsOverlays()
    {
        var readings = PowerStatusReader.MapModes(new NativePowerModes(
            new Guid("ded574b5-45a0-4f42-8737-46345c09c238"),
            new Guid("961cc777-2547-4f9d-8174-7d86181b8a7a")));

        Assert.Equal((int)PowerMode.BestPerformance, Reading(readings, "power.mode").Value);
        Assert.Equal((int)PowerMode.BestEfficiency, Reading(readings, "power.mode_effective").Value);
    }

    [Fact]
    public void BalancedIsTheEmptyOverlayAndUnknownGuidsAreNotGuessed()
    {
        var readings = PowerStatusReader.MapModes(new NativePowerModes(Guid.Empty, Guid.NewGuid()));

        Assert.Equal((int)PowerMode.Balanced, Reading(readings, "power.mode").Value);
        Assert.Equal("power_mode_unknown", Reading(readings, "power.mode_effective").ErrorCode);
    }

    [Fact]
    public void FailedModeQueryIsAFault()
    {
        var reading = Reading(PowerStatusReader.MapModes(new NativePowerModes(null, null)), "power.mode");

        Assert.Equal(ReadingStatus.Fault, reading.Status);
        Assert.Equal("power_mode_failed", reading.ErrorCode);
    }

    private static TelemetryReading Reading(IReadOnlyList<TelemetryReading> readings, string id)
    {
        return Assert.Single(readings, reading => reading.Id == id);
    }
}
