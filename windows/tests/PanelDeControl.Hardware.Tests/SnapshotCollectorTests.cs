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

        Assert.Equal("ROG Xbox Ally X", snapshot.DeviceModel);
        Assert.Equal(0, Reading(snapshot, "battery.level").Value);
        Assert.Equal(0, Reading(snapshot, "cpu.load").Value);
        Assert.Equal(0, Reading(snapshot, "gpu.load").Value);
        Assert.All(
            snapshot.Readings.Where(reading => reading.Id is "battery.level" or "power.ac" or "cpu.load" or "cpu.temperature" or "gpu.load" or "gpu.temperature"),
            reading => Assert.Equal(ReadingStatus.Available, reading.Status));
        Assert.Equal("power_reading_not_found", Reading(snapshot, "power.draw").ErrorCode);
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
            new FixedPowerReader(AvailablePower()),
            FixedAccessProbe.Full);

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
            new FixedPowerReader(AvailablePower()),
            FixedAccessProbe.Full);

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
            new FixedPowerReader(AvailablePower()),
            FixedAccessProbe.Full);

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

    [Fact]
    public void AllZeroSensorOutputIsNotReportedAsARealTemperature()
    {
        var collector = CreateCollector(
            hardwareReadings: new[]
            {
                Candidate("cpu/load/total", HardwareKind.Cpu, SensorKind.Load, "CPU Total", 0),
                Candidate("cpu/temp/package", HardwareKind.Cpu, SensorKind.Temperature, "CPU Package", 0),
                Candidate("gpu/load/core", HardwareKind.Gpu, SensorKind.Load, "GPU Core", 0),
                Candidate("gpu/temp/core", HardwareKind.Gpu, SensorKind.Temperature, "GPU Core", 0),
            },
            powerReadings: AvailablePower());

        var snapshot = collector.Capture();

        Assert.Equal(ReadingStatus.Available, Reading(snapshot, "cpu.load").Status);
        Assert.Equal(0, Reading(snapshot, "cpu.load").Value);
        foreach (var id in new[] { "cpu.temperature", "gpu.temperature" })
        {
            var reading = Reading(snapshot, id);
            Assert.Equal(ReadingStatus.Unavailable, reading.Status);
            Assert.Null(reading.Value);
            Assert.Equal("sensor_implausible", reading.ErrorCode);
        }
    }

    [Theory]
    [InlineData(SensorKind.Temperature, "CPU Package", double.NaN)]
    [InlineData(SensorKind.Temperature, "CPU Package", 130)]
    [InlineData(SensorKind.Temperature, "CPU Package", -5)]
    [InlineData(SensorKind.Load, "CPU Total", 101)]
    [InlineData(SensorKind.Load, "CPU Total", double.PositiveInfinity)]
    public void ImplausibleValuesAreUnavailable(SensorKind kind, string name, double value)
    {
        var id = kind == SensorKind.Temperature ? "cpu.temperature" : "cpu.load";
        var collector = CreateCollector(
            hardwareReadings: new[] { Candidate("cpu/x", HardwareKind.Cpu, kind, name, value) },
            powerReadings: AvailablePower());

        var reading = Reading(collector.Capture(), id);

        Assert.Equal(ReadingStatus.Unavailable, reading.Status);
        Assert.Equal("sensor_implausible", reading.ErrorCode);
    }

    [Theory]
    [InlineData(false, true, "sensor_driver_missing")]
    [InlineData(true, false, "sensor_elevation_required")]
    [InlineData(false, false, "sensor_driver_missing")]
    public void TemperaturesNeedDriverAndElevationWhileLoadStillReads(
        bool hasDriver,
        bool isElevated,
        string expectedError)
    {
        var collector = CreateCollector(
            hardwareReadings: new[]
            {
                Candidate("cpu/load/total", HardwareKind.Cpu, SensorKind.Load, "CPU Total", 37),
                Candidate("cpu/temp/package", HardwareKind.Cpu, SensorKind.Temperature, "CPU Package", 61),
                Candidate("gpu/temp/core", HardwareKind.Gpu, SensorKind.Temperature, "GPU Core", 58),
            },
            powerReadings: AvailablePower(),
            accessProbe: new FixedAccessProbe(new SensorAccess(isElevated, hasDriver)));

        var snapshot = collector.Capture();

        Assert.Equal(37, Reading(snapshot, "cpu.load").Value);
        Assert.Equal(58, Reading(snapshot, "gpu.temperature").Value);
        var cpuTemperature = Reading(snapshot, "cpu.temperature");
        Assert.Equal(ReadingStatus.PermissionRequired, cpuTemperature.Status);
        Assert.Null(cpuTemperature.Value);
        Assert.Equal(expectedError, cpuTemperature.ErrorCode);
    }

    [Fact]
    public void RecognizedIdentityIsReadOnceAcrossPolls()
    {
        var identityReader = new CountingIdentityReader();
        var collector = new SnapshotCollector(
            new FixedClock(),
            identityReader,
            new FixedHardwareReader(Array.Empty<SensorCandidate>()),
            new FixedPowerReader(AvailablePower()),
            FixedAccessProbe.Full);

        collector.Capture();
        collector.Capture();

        Assert.Equal(1, identityReader.ReadCount);
    }

    [Fact]
    public void MissingValueIsNotFoundRatherThanImplausible()
    {
        var collector = CreateCollector(
            hardwareReadings: new[]
            {
                new SensorCandidate("gpu/temp/core", HardwareKind.Gpu, SensorKind.Temperature, "GPU Core", null, "gpu/temp/core"),
            },
            powerReadings: AvailablePower());

        Assert.Equal("sensor_not_found", Reading(collector.Capture(), "gpu.temperature").ErrorCode);
    }

    [Fact]
    public void FailingAccessProbeIsTreatedAsMissingAccess()
    {
        var collector = CreateCollector(
            hardwareReadings: new[]
            {
                Candidate("cpu/temp/package", HardwareKind.Cpu, SensorKind.Temperature, "CPU Package", 61),
            },
            powerReadings: AvailablePower(),
            accessProbe: new ThrowingAccessProbe());

        var reading = Reading(collector.Capture(), "cpu.temperature");

        Assert.Equal(ReadingStatus.PermissionRequired, reading.Status);
        Assert.Equal("sensor_permission_required", reading.ErrorCode);
    }

    private static SnapshotCollector CreateCollector(
        IReadOnlyList<SensorCandidate> hardwareReadings,
        IReadOnlyList<TelemetryReading> powerReadings,
        ISensorAccessProbe? accessProbe = null)
    {
        return new SnapshotCollector(
            new FixedClock(),
            new FixedIdentityReader(),
            new FixedHardwareReader(hardwareReadings),
            new FixedPowerReader(powerReadings),
            accessProbe ?? FixedAccessProbe.Full);
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
                DeviceCatalogResource.TryLoad(),
                "ASUSTeK COMPUTER INC.",
                "ROG Xbox Ally X RC73XA_RC73XA",
                "RC73XA");
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
            return DeviceIdentity.FromDmi(
                DeviceCatalogResource.TryLoad(),
                "Contoso",
                "Some Laptop 15",
                "X1");
        }
    }

    private sealed class FixedAccessProbe : ISensorAccessProbe
    {
        public static readonly FixedAccessProbe Full = new(new SensorAccess(true, true));

        private readonly SensorAccess access;

        public FixedAccessProbe(SensorAccess access)
        {
            this.access = access;
        }

        public SensorAccess Probe()
        {
            return access;
        }
    }

    private sealed class ThrowingAccessProbe : ISensorAccessProbe
    {
        public SensorAccess Probe()
        {
            throw new InvalidOperationException("registry unavailable");
        }
    }

    private sealed class CountingIdentityReader : IDeviceIdentityReader
    {
        public int ReadCount { get; private set; }

        public DeviceIdentity Read()
        {
            ReadCount++;
            return new FixedIdentityReader().Read();
        }
    }
}
