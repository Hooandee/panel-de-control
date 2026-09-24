using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public sealed class ServiceBackedSnapshotProvider : IHardwareSnapshotProvider
{
    public static readonly TimeSpan MaximumServiceAge = TimeSpan.FromSeconds(10);

    private static readonly HashSet<string> ServiceSensorIds = new(StringComparer.Ordinal)
    {
        "cpu.temperature",
        "gpu.temperature",
        "cpu.load",
        "gpu.load",
        "fan.cpu.rpm",
        "fan.gpu.rpm",
        BatteryHealth.DesignCapacityId,
        BatteryHealth.FullCapacityId,
        BatteryHealth.HealthId,
        BatteryHealth.CyclesId,
    };

    private readonly IHardwareSnapshotProvider local;
    private readonly IServiceSnapshotSource service;
    private readonly IClock clock;

    public ServiceBackedSnapshotProvider(
        IHardwareSnapshotProvider local,
        IServiceSnapshotSource service,
        IClock clock)
    {
        this.local = local;
        this.service = service;
        this.clock = clock;
    }

    public HardwareSnapshot Capture()
    {
        var localSnapshot = local.Capture();
        ServiceSnapshotResult result;
        try
        {
            result = service.Read();
        }
        catch
        {
            result = ServiceSnapshotResult.Unavailable;
        }

        var serviceReadings = FreshServiceReadings(result);
        var merged = localSnapshot.Readings.Select(reading =>
            Merge(reading, serviceReadings, result.Outcome)).ToList();
        if (!localSnapshot.Readings.Any(reading => reading.ErrorCode == "device_not_supported"))
        {
            var localIds = new HashSet<string>(localSnapshot.Readings.Select(reading => reading.Id), StringComparer.Ordinal);
            merged.AddRange(serviceReadings.Values.Where(reading =>
                reading.Id is "fan.cpu.rpm" or "fan.gpu.rpm" && !localIds.Contains(reading.Id) &&
                (reading.Status != ReadingStatus.Available || IsPlausible(reading))));
        }
        return new HardwareSnapshot(localSnapshot.CapturedAtUtc, localSnapshot.DeviceModel, merged, localSnapshot.DeviceMaxWatts);
    }

    private IReadOnlyDictionary<string, TelemetryReading> FreshServiceReadings(ServiceSnapshotResult result)
    {
        var snapshot = result.Snapshot;
        if (result.Outcome != ServiceSnapshotOutcome.Received || snapshot is null)
        {
            return new Dictionary<string, TelemetryReading>();
        }

        var age = clock.UtcNow - snapshot.CapturedAtUtc;
        if (age < TimeSpan.Zero || age > MaximumServiceAge)
        {
            return new Dictionary<string, TelemetryReading>();
        }

        return snapshot.Readings
            .Where(reading => ServiceSensorIds.Contains(reading.Id))
            .GroupBy(reading => reading.Id, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.First(), StringComparer.Ordinal);
    }

    private static TelemetryReading Merge(
        TelemetryReading localReading,
        IReadOnlyDictionary<string, TelemetryReading> serviceReadings,
        ServiceSnapshotOutcome outcome)
    {
        if (!ServiceSensorIds.Contains(localReading.Id) ||
            localReading.ErrorCode == "device_not_supported")
        {
            return localReading;
        }

        if (serviceReadings.TryGetValue(localReading.Id, out var serviceReading))
        {
            if (serviceReading.Status == ReadingStatus.Available)
            {
                return IsPlausible(serviceReading) ? serviceReading : localReading;
            }

            return localReading.Status == ReadingStatus.Available ? localReading : serviceReading;
        }

        if (localReading.Status == ReadingStatus.PermissionRequired)
        {
            return TelemetryReading.Unavailable(
                localReading.Id,
                localReading.Label,
                localReading.Unit,
                ReadingStatus.PermissionRequired,
                outcome == ServiceSnapshotOutcome.NotRunning ? "service_not_running" : "service_unavailable");
        }

        return localReading;
    }

    private static bool IsPlausible(TelemetryReading reading)
    {
        var batteryKind = BatteryHealth.KindOf(reading.Id);
        var kind = batteryKind != SensorKind.Unknown
            ? batteryKind
            : reading.Id.EndsWith(".temperature", StringComparison.Ordinal)
                ? SensorKind.Temperature
                : reading.Id.EndsWith(".rpm", StringComparison.Ordinal) ? SensorKind.Fan : SensorKind.Load;
        return SensorPlausibility.IsPlausible(kind, reading.Value);
    }
}
