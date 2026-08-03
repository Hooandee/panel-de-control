using PanelDeControl.Core.Telemetry;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class TelemetryContractTests
{
    [Fact]
    public void AvailableZeroRemainsARealReading()
    {
        var reading = TelemetryReading.Available(
            "fan.rpm",
            "Ventilador",
            0,
            "RPM",
            "hardware/fan/0");

        Assert.Equal(ReadingStatus.Available, reading.Status);
        Assert.Equal(0, reading.Value);
        Assert.Null(reading.ErrorCode);
    }

    [Fact]
    public void UnavailableReadingCannotCarryAValue()
    {
        var reading = TelemetryReading.Unavailable(
            "cpu.temperature",
            "CPU",
            "°C",
            ReadingStatus.PermissionRequired,
            "sensor_permission_required");

        Assert.Equal(ReadingStatus.PermissionRequired, reading.Status);
        Assert.Null(reading.Value);
        Assert.Equal("sensor_permission_required", reading.ErrorCode);
    }

    [Fact]
    public void SnapshotRoundTripPreservesTelemetryMeaning()
    {
        var capturedAt = new DateTimeOffset(2026, 7, 29, 20, 30, 0, TimeSpan.Zero);
        var snapshot = new HardwareSnapshot(
            capturedAt,
            "ROG Xbox Ally X RC73XA_RC73XA",
            new[]
            {
                TelemetryReading.Available("battery.level", "Batería", 82, "%", "win32/power"),
                TelemetryReading.Unavailable(
                    "gpu.temperature",
                    "GPU",
                    "°C",
                    ReadingStatus.Unavailable,
                    "sensor_not_found"),
            });

        var payload = TelemetryWireCodec.Serialize(snapshot);
        var restored = TelemetryWireCodec.Deserialize(payload);

        Assert.Equal(capturedAt, restored.CapturedAtUtc);
        Assert.Equal("ROG Xbox Ally X RC73XA_RC73XA", restored.DeviceModel);
        Assert.Collection(
            restored.Readings,
            reading =>
            {
                Assert.Equal(ReadingStatus.Available, reading.Status);
                Assert.Equal(82, reading.Value);
            },
            reading =>
            {
                Assert.Equal(ReadingStatus.Unavailable, reading.Status);
                Assert.Null(reading.Value);
                Assert.Equal("sensor_not_found", reading.ErrorCode);
            });
    }

    [Fact]
    public void UnknownWireStatusFailsClosed()
    {
        const string payload =
            """
            {
              "captured_at_utc":"2026-07-29T20:30:00Z",
              "device_model":"ROG Xbox Ally X RC73XA_RC73XA",
              "readings":[{
                "id":"cpu.temperature",
                "label":"CPU",
                "status":999,
                "unit":"°C",
                "value":74,
                "source":"hardware/cpu/0",
                "error_code":null
              }]
            }
            """;

        var restored = TelemetryWireCodec.Deserialize(payload);
        var reading = Assert.Single(restored.Readings);

        Assert.Equal(ReadingStatus.Fault, reading.Status);
        Assert.Null(reading.Value);
        Assert.Equal("invalid_reading_status", reading.ErrorCode);
    }
}
