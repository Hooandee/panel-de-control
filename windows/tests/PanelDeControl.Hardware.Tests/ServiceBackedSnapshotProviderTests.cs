using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ServiceBackedSnapshotProviderTests
{
    private static readonly DateTimeOffset Now = new(2026, 9, 22, 22, 0, 0, TimeSpan.Zero);

    [Fact]
    public void FreshPlausibleServiceReadingReplacesTheLocalOne()
    {
        var provider = Provider(
            Local(TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.PermissionRequired, "sensor_elevation_required")),
            Received(Now.AddSeconds(-1), TelemetryReading.Available("cpu.temperature", "CPU", 64, "°C", "service/lhm")));

        var reading = Single(provider.Capture(), "cpu.temperature");

        Assert.Equal(ReadingStatus.Available, reading.Status);
        Assert.Equal(64, reading.Value);
        Assert.Equal("service/lhm", reading.Source);
    }

    [Fact]
    public void StaleServiceSnapshotIsIgnored()
    {
        var provider = Provider(
            Local(TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.PermissionRequired, "sensor_elevation_required")),
            Received(Now - ServiceBackedSnapshotProvider.MaximumServiceAge - TimeSpan.FromSeconds(1),
                TelemetryReading.Available("cpu.temperature", "CPU", 64, "°C", "service/lhm")));

        var reading = Single(provider.Capture(), "cpu.temperature");

        Assert.Null(reading.Value);
        Assert.Equal("service_unavailable", reading.ErrorCode);
    }

    [Fact]
    public void ServiceFromTheFutureIsIgnored()
    {
        var provider = Provider(
            Local(TelemetryReading.Available("cpu.load", "CPU", 12, "%", "local")),
            Received(Now.AddMinutes(5), TelemetryReading.Available("cpu.load", "CPU", 90, "%", "service")));

        Assert.Equal(12, Single(provider.Capture(), "cpu.load").Value);
    }

    [Theory]
    [InlineData(ServiceSnapshotOutcome.NotRunning, "service_not_running")]
    [InlineData(ServiceSnapshotOutcome.Unavailable, "service_unavailable")]
    public void MissingServiceExplainsWhyCpuTemperatureIsBlocked(ServiceSnapshotOutcome outcome, string expected)
    {
        var provider = Provider(
            Local(TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.PermissionRequired, "sensor_elevation_required")),
            new ServiceSnapshotResult(outcome, null));

        var reading = Single(provider.Capture(), "cpu.temperature");

        Assert.Equal(ReadingStatus.PermissionRequired, reading.Status);
        Assert.Equal(expected, reading.ErrorCode);
    }

    [Fact]
    public void ServiceDriverProblemIsReportedWhenLocalHasNoValue()
    {
        var provider = Provider(
            Local(TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.PermissionRequired, "sensor_elevation_required")),
            Received(Now, TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.PermissionRequired, "sensor_driver_missing")));

        Assert.Equal("sensor_driver_missing", Single(provider.Capture(), "cpu.temperature").ErrorCode);
    }

    [Fact]
    public void LocalValueWinsOverAServiceFailure()
    {
        var provider = Provider(
            Local(TelemetryReading.Available("gpu.temperature", "GPU", 55, "°C", "local")),
            Received(Now, TelemetryReading.Unavailable("gpu.temperature", "GPU", "°C", ReadingStatus.Fault, "sensor_provider_failed")));

        Assert.Equal(55, Single(provider.Capture(), "gpu.temperature").Value);
    }

    [Fact]
    public void NonSensorReadingsAndUnsupportedDevicesAreNeverTakenFromTheService()
    {
        var provider = Provider(
            Local(
                TelemetryReading.Available("battery.level", "Batería", 80, "%", "win32/power"),
                TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C", ReadingStatus.Unavailable, "device_not_supported")),
            Received(Now,
                TelemetryReading.Available("battery.level", "Batería", 10, "%", "service"),
                TelemetryReading.Available("cpu.temperature", "CPU", 60, "°C", "service")));

        var snapshot = provider.Capture();

        Assert.Equal(80, Single(snapshot, "battery.level").Value);
        Assert.Equal("device_not_supported", Single(snapshot, "cpu.temperature").ErrorCode);
    }

    [Fact]
    public void ThrowingServiceSourceKeepsLocalReadings()
    {
        var provider = new ServiceBackedSnapshotProvider(
            new FixedProvider(Local(TelemetryReading.Available("cpu.load", "CPU", 7, "%", "local"))),
            new ThrowingSource(),
            new FixedClock());

        Assert.Equal(7, Single(provider.Capture(), "cpu.load").Value);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(3800)]
    [InlineData(10000)]
    public void FreshServiceFansReachConsumersWithoutLocalFanDefinitions(double rpm)
    {
        var provider = Provider(Local(), Received(Now,
            TelemetryReading.Available("fan.cpu.rpm", "Ventilador 1", rpm, "RPM", "asus/atk-dsts"),
            TelemetryReading.Available("fan.gpu.rpm", "Ventilador 2", 3700, "RPM", "asus/atk-dsts")));

        Assert.Equal(rpm, Single(provider.Capture(), "fan.cpu.rpm").Value);
        Assert.Equal(3700, Single(provider.Capture(), "fan.gpu.rpm").Value);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(10001)]
    public void ImplausibleServiceOnlyFansNeverPublishANumber(double rpm)
    {
        var snapshot = Provider(Local(), Received(Now,
            TelemetryReading.Available("fan.cpu.rpm", "Ventilador 1", rpm, "RPM", "asus/atk-dsts"))).Capture();
        Assert.DoesNotContain(snapshot.Readings, r => r.Id == "fan.cpu.rpm" && r.Value.HasValue);
    }

    [Theory]
    [InlineData(-11)]
    [InlineData(1)]
    public void StaleOrFutureFansAreNotAppended(int seconds)
    {
        var snapshot = Provider(Local(), Received(Now.AddSeconds(seconds),
            TelemetryReading.Available("fan.cpu.rpm", "Ventilador 1", 3800, "RPM", "asus/atk-dsts"))).Capture();
        Assert.DoesNotContain(snapshot.Readings, r => r.Id == "fan.cpu.rpm");
    }

    [Fact]
    public void UnsupportedDevicesNeverAppendServiceFans()
    {
        var snapshot = Provider(Local(TelemetryReading.Unavailable("cpu.temperature", "CPU", "°C",
                ReadingStatus.Unavailable, "device_not_supported")),
            Received(Now, TelemetryReading.Available("fan.cpu.rpm", "Ventilador 1", 3800, "RPM", "asus/atk-dsts"))).Capture();
        Assert.DoesNotContain(snapshot.Readings, r => r.Id == "fan.cpu.rpm");
    }

    private static ServiceBackedSnapshotProvider Provider(HardwareSnapshot local, ServiceSnapshotResult service)
    {
        return new ServiceBackedSnapshotProvider(new FixedProvider(local), new FixedSource(service), new FixedClock());
    }

    private static HardwareSnapshot Local(params TelemetryReading[] readings)
    {
        return new HardwareSnapshot(Now, "ROG Xbox Ally X", readings);
    }

    private static ServiceSnapshotResult Received(DateTimeOffset capturedAt, params TelemetryReading[] readings)
    {
        return new ServiceSnapshotResult(
            ServiceSnapshotOutcome.Received,
            new HardwareSnapshot(capturedAt, "ROG Xbox Ally X", readings));
    }

    private static TelemetryReading Single(HardwareSnapshot snapshot, string id)
    {
        return Assert.Single(snapshot.Readings, reading => reading.Id == id);
    }

    private sealed class FixedClock : IClock
    {
        public DateTimeOffset UtcNow => Now;
    }

    private sealed class FixedProvider : IHardwareSnapshotProvider
    {
        private readonly HardwareSnapshot snapshot;

        public FixedProvider(HardwareSnapshot snapshot)
        {
            this.snapshot = snapshot;
        }

        public HardwareSnapshot Capture()
        {
            return snapshot;
        }
    }

    private sealed class FixedSource : IServiceSnapshotSource
    {
        private readonly ServiceSnapshotResult result;

        public FixedSource(ServiceSnapshotResult result)
        {
            this.result = result;
        }

        public ServiceSnapshotResult Read()
        {
            return result;
        }
    }

    private sealed class ThrowingSource : IServiceSnapshotSource
    {
        public ServiceSnapshotResult Read()
        {
            throw new IOException("pipe broke");
        }
    }
}
