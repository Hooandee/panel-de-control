using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public sealed class SnapshotCollector : IHardwareSnapshotProvider
{
    private static readonly SensorDefinition[] SensorDefinitions =
    {
        new(
            "cpu.load",
            "CPU",
            "%",
            HardwareKind.Cpu,
            SensorKind.Load,
            new[] { "CPU Total", "CPU Core" }),
        new(
            "cpu.temperature",
            "CPU",
            "°C",
            HardwareKind.Cpu,
            SensorKind.Temperature,
            new[] { "CPU Package", "Core (Tctl/Tdie)", "Core" }),
        new(
            "gpu.load",
            "GPU",
            "%",
            HardwareKind.Gpu,
            SensorKind.Load,
            new[] { "GPU Core", "GPU Total" }),
        new(
            "gpu.temperature",
            "GPU",
            "°C",
            HardwareKind.Gpu,
            SensorKind.Temperature,
            new[] { "GPU Core", "GPU Hot Spot" }),
    };

    private static readonly PowerDefinition[] PowerDefinitions =
    {
        new("battery.level", "Batería", "%"),
        new("power.ac", "Alimentación", "bool"),
    };

    private readonly IClock clock;
    private readonly IDeviceIdentityReader identityReader;
    private readonly IHardwareReader hardwareReader;
    private readonly IPowerStatusReader powerReader;

    public SnapshotCollector(
        IClock clock,
        IDeviceIdentityReader identityReader,
        IHardwareReader hardwareReader,
        IPowerStatusReader powerReader)
    {
        this.clock = clock;
        this.identityReader = identityReader;
        this.hardwareReader = hardwareReader;
        this.powerReader = powerReader;
    }

    public HardwareSnapshot Capture()
    {
        var identity = ReadIdentity();
        var readings = new List<TelemetryReading>();
        readings.AddRange(ReadPower());
        readings.AddRange(ReadHardware(identity.IsInitialTarget));

        return new HardwareSnapshot(clock.UtcNow, identity.ProductName, readings);
    }

    private DeviceIdentity ReadIdentity()
    {
        try
        {
            return identityReader.Read();
        }
        catch
        {
            return DeviceIdentity.FromDmi(null, null);
        }
    }

    private IEnumerable<TelemetryReading> ReadPower()
    {
        try
        {
            var readings = powerReader.Read();
            return PowerDefinitions.Select(definition =>
                readings.FirstOrDefault(reading => reading.Id == definition.Id) ??
                TelemetryReading.Unavailable(
                    definition.Id,
                    definition.Label,
                    definition.Unit,
                    ReadingStatus.Unavailable,
                    "power_reading_not_found"));
        }
        catch (UnauthorizedAccessException)
        {
            return UnavailablePower(ReadingStatus.PermissionRequired, "power_permission_required");
        }
        catch
        {
            return UnavailablePower(ReadingStatus.Fault, "power_provider_failed");
        }
    }

    private IEnumerable<TelemetryReading> ReadHardware(bool isInitialTarget)
    {
        if (!isInitialTarget)
        {
            return UnavailableHardware(
                ReadingStatus.Unavailable,
                "device_not_supported");
        }

        IReadOnlyList<SensorCandidate> candidates;
        try
        {
            candidates = hardwareReader.Read();
        }
        catch (UnauthorizedAccessException)
        {
            return UnavailableHardware(
                ReadingStatus.PermissionRequired,
                "sensor_permission_required");
        }
        catch
        {
            return UnavailableHardware(ReadingStatus.Fault, "sensor_provider_failed");
        }

        return SensorDefinitions.Select(definition =>
        {
            var selected = SensorSelector.Select(
                candidates,
                definition.HardwareKind,
                definition.SensorKind,
                definition.PreferredNames);
            return selected is null
                ? TelemetryReading.Unavailable(
                    definition.Id,
                    definition.Label,
                    definition.Unit,
                    ReadingStatus.Unavailable,
                    "sensor_not_found")
                : TelemetryReading.Available(
                    definition.Id,
                    definition.Label,
                    selected.Value!.Value,
                    definition.Unit,
                    selected.Source);
        });
    }

    private static IEnumerable<TelemetryReading> UnavailablePower(
        ReadingStatus status,
        string errorCode)
    {
        return PowerDefinitions.Select(definition => TelemetryReading.Unavailable(
            definition.Id,
            definition.Label,
            definition.Unit,
            status,
            errorCode));
    }

    private static IEnumerable<TelemetryReading> UnavailableHardware(
        ReadingStatus status,
        string errorCode)
    {
        return SensorDefinitions.Select(definition => TelemetryReading.Unavailable(
            definition.Id,
            definition.Label,
            definition.Unit,
            status,
            errorCode));
    }

    private sealed record SensorDefinition(
        string Id,
        string Label,
        string Unit,
        HardwareKind HardwareKind,
        SensorKind SensorKind,
        IReadOnlyList<string> PreferredNames);

    private sealed record PowerDefinition(string Id, string Label, string Unit);
}
