using PanelDeControl.Core.Telemetry;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class SnapshotScaleTests
{
    [Fact]
    public void DeviceCeilingRoundTripsAndStaysOptional()
    {
        var withScale = new HardwareSnapshot(DateTimeOffset.UnixEpoch, "ROG Xbox Ally X", Array.Empty<TelemetryReading>(), 35);
        var withoutScale = new HardwareSnapshot(DateTimeOffset.UnixEpoch, "Unknown device", Array.Empty<TelemetryReading>());

        Assert.Equal(35, TelemetryWireCodec.Deserialize(TelemetryWireCodec.Serialize(withScale)).DeviceMaxWatts);
        var wire = TelemetryWireCodec.Serialize(withoutScale);
        Assert.DoesNotContain("device_max_watts", wire);
        Assert.Null(TelemetryWireCodec.Deserialize(wire).DeviceMaxWatts);
    }

    [Fact]
    public void NonPositiveCeilingIsDropped()
    {
        Assert.Null(new HardwareSnapshot(DateTimeOffset.UnixEpoch, "x", Array.Empty<TelemetryReading>(), 0).DeviceMaxWatts);
    }
}
