using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class SnapshotCollectorTests
{
    [Fact]
    public void CapturesRealZeroValuesWithoutTreatingThemAsMissing()
    {
        var collector = CreateCollector(
            hardwareReadings: new[]
            {
                Candidate("cpu/load/total", HardwareKind.Cpu, SensorKind.Load, "CPU Total", 0),
                Candidate("cpu/temp/package", HardwareKind.Cpu, SensorKind.Temperature, "CPU Package", 68),
                Candidate("gpu/load/core", HardwareKind.Gpu, SensorKind.Load, "GPU Core", 0),
                Candidate("gpu/temp/core", HardwareKind.Gpu, SensorKind.Temperature, "GPU Core", 65),
            },
            powerReadings: new[]
            {
                TelemetryReading.Available("battery.level", "Batería", 0, "%", "win32/power"),
                TelemetryReading.Available("power.ac", "Alimentación", 0, "bool", "win32/power"),
            });

        var snapshot = collector.Capture();

        Assert.Equal("ROG Xbox Ally X RC73XA_RC73XA", snapshot.DeviceModel);
        Assert.Equal(0, Reading(snapshot, "battery.level").Value);
        Assert.Equal(0, Reading(snapshot, "cpu.load").Value);
        Assert.Equal(0, Reading(snapshot, "gpu.load").Value);
        Assert.All(snapshot.Readings, reading => Assert.Equal(ReadingStatus.Available, reading.Status));
    }

    [Fact]
    public void MissingTemperatureIsExplicitlyUnavailable()
    {
        var collector = CreateCollector(
            hardwareReadings: Array.Empty<SensorCandidate>(),
            powerReadings: AvailablePower());

        var snapshot = collector.Capture();

        var cpuTemperature = Reading(snapshot, "cpu.temperature");
        Assert.Equal(ReadingStatus.Unavailable, cpuTemperature.Status);
        Assert.Null(cpuTemperature.Value);
        Assert.Equal("sensor_not_found", cpuTemperature.ErrorCode);
    }

    [Fact]
    public void HardwarePermissionFailureIsIsolatedFromPowerReadings()
    {
        var collector = new SnapshotCollector(
            new FixedClock(),
            new FixedIdentityReader(),
            new ThrowingHardwareReader(new UnauthorizedAccessException("denied")),
            new FixedPowerReader(AvailablePower()));

        var snapshot = collector.Capture();

        Assert.Equal(82, Reading(snapshot, "battery.level").Value);
        Assert.Equal(ReadingStatus.PermissionRequired, Reading(snapshot, "cpu.temperature").Status);
        Assert.Equal(ReadingStatus.PermissionRequired, Reading(snapshot, "gpu.temperature").Status);
        Assert.Equal("sensor_permission_required", Reading(snapshot, "cpu.temperature").ErrorCode);
    }

    [Fact]
    public void UnexpectedHardwareFailureProducesFaultWithoutRawExceptionText()
    {
        var collector = new SnapshotCollector(
            new FixedClock(),
            new FixedIdentityReader(),
            new ThrowingHardwareReader(new InvalidOperationException("private machine path")),
            new FixedPowerReader(AvailablePower()));

        var snapshot = collector.Capture();

        var reading = Reading(snapshot, "cpu.temperature");
        Assert.Equal(ReadingStatus.Fault, reading.Status);
        Assert.Equal("sensor_provider_failed", reading.ErrorCode);
        Assert.DoesNotContain("private machine path", TelemetryWireCodec.Serialize(snapshot));
    }

    [Fact]
    public void UnsupportedDeviceDoesNotInvokeHardwareProvider()
    {
        var hardwareReader = new CountingHardwareReader();
        var collector = new SnapshotCollector(
            new FixedClock(),
            new UnsupportedIdentityReader(),
            hardwareReader,
            new FixedPowerReader(AvailablePower()));

        var snapshot = collector.Capture();

        Assert.Equal(0, hardwareReader.ReadCount);
        Assert.Equal(82, Reading(snapshot, "battery.level").Value);
        Assert.Equal(
            "device_not_supported",
            Reading(snapshot, "cpu.temperature").ErrorCode);
        Assert.Equal(
            "device_not_supported",
            Reading(snapshot, "gpu.temperature").ErrorCode);
    }

    private static SnapshotCollector CreateCollector(
        IReadOnlyList<SensorCandidate> hardwareReadings,
        IReadOnlyList<TelemetryReading> powerReadings)
    {
        return new SnapshotCollector(
            new FixedClock(),
            new FixedIdentityReader(),
            new FixedHardwareReader(hardwareReadings),
            new FixedPowerReader(powerReadings));
    }

    private static IReadOnlyList<TelemetryReading> AvailablePower()
    {
        return new[]
        {
            TelemetryReading.Available("battery.level", "Batería", 82, "%", "win32/power"),
            TelemetryReading.Available("power.ac", "Alimentación", 1, "bool", "win32/power"),
        };
    }

    private static SensorCandidate Candidate(
        string identifier,
        HardwareKind hardwareKind,
        SensorKind sensorKind,
        string name,
        double value)
    {
        return new SensorCandidate(identifier, hardwareKind, sensorKind, name, value, identifier);
    }

    private static TelemetryReading Reading(HardwareSnapshot snapshot, string id)
    {
        return Assert.Single(snapshot.Readings, reading => reading.Id == id);
    }

    private sealed class FixedClock : IClock
    {
        public DateTimeOffset UtcNow { get; } =
            new(2026, 7, 29, 20, 30, 0, TimeSpan.Zero);
    }

    private sealed class FixedIdentityReader : IDeviceIdentityReader
    {
        public DeviceIdentity Read()
        {
            return DeviceIdentity.FromDmi(
                "ASUSTeK COMPUTER INC.",
                "ROG Xbox Ally X RC73XA_RC73XA");
        }
    }

    private sealed class FixedHardwareReader : IHardwareReader
    {
        private readonly IReadOnlyList<SensorCandidate> readings;

        public FixedHardwareReader(IReadOnlyList<SensorCandidate> readings)
        {
            this.readings = readings;
        }

        public IReadOnlyList<SensorCandidate> Read()
        {
            return readings;
        }
    }

    private sealed class CountingHardwareReader : IHardwareReader
    {
        public int ReadCount { get; private set; }

        public IReadOnlyList<SensorCandidate> Read()
        {
            ReadCount++;
            return Array.Empty<SensorCandidate>();
        }
    }

    private sealed class ThrowingHardwareReader : IHardwareReader
    {
        private readonly Exception exception;

        public ThrowingHardwareReader(Exception exception)
        {
            this.exception = exception;
        }

        public IReadOnlyList<SensorCandidate> Read()
        {
            throw exception;
        }
    }

    private sealed class FixedPowerReader : IPowerStatusReader
    {
        private readonly IReadOnlyList<TelemetryReading> readings;

        public FixedPowerReader(IReadOnlyList<TelemetryReading> readings)
        {
            this.readings = readings;
        }

        public IReadOnlyList<TelemetryReading> Read()
        {
            return readings;
        }
    }

    private sealed class UnsupportedIdentityReader : IDeviceIdentityReader
    {
        public DeviceIdentity Read()
        {
            return DeviceIdentity.FromDmi("Valve", "Jupiter");
        }
    }
}
