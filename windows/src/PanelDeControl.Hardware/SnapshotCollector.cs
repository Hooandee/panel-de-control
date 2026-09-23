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
        new("power.draw", "Consumo", "W"),
        new("battery.time_remaining", "Autonomía", "min"),
        new("power.mode", "Modo de energía", "mode"),
        new("power.mode_effective", "Modo de energía", "mode"),
    };

    private readonly IClock clock;
    private readonly IDeviceIdentityReader identityReader;
    private readonly IHardwareReader hardwareReader;
    private readonly IPowerStatusReader powerReader;
    private readonly ISensorAccessProbe accessProbe;
    private DeviceIdentity? cachedIdentity;

    public SnapshotCollector(
        IClock clock,
        IDeviceIdentityReader identityReader,
        IHardwareReader hardwareReader,
        IPowerStatusReader powerReader,
        ISensorAccessProbe accessProbe)
    {
        this.clock = clock;
        this.identityReader = identityReader;
        this.hardwareReader = hardwareReader;
        this.powerReader = powerReader;
        this.accessProbe = accessProbe;
    }

    public HardwareSnapshot Capture()
    {
        var identity = ReadIdentity();
        var readings = new List<TelemetryReading>();
        readings.AddRange(ReadPower());
        readings.AddRange(ReadHardware(identity.IsRecognized));

        return new HardwareSnapshot(clock.UtcNow, identity.DisplayName, readings, identity.Profile?.Limits.TdpMaxCharger);
    }

    private DeviceIdentity ReadIdentity()
    {
        if (cachedIdentity is not null)
        {
            return cachedIdentity;
        }

        try
        {
            var identity = identityReader.Read();
            if (identity.IsRecognized || identity.ProductName != DeviceIdentity.Unrecognized().ProductName)
            {
                cachedIdentity = identity;
            }

            return identity;
        }
        catch
        {
            return DeviceIdentity.Unrecognized();
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

    private IEnumerable<TelemetryReading> ReadHardware(bool isRecognized)
    {
        if (!isRecognized)
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

        var missingAccess = MissingTemperatureAccess();
        return SensorDefinitions.Select(definition =>
        {
            if (definition.HardwareKind == HardwareKind.Cpu &&
                definition.SensorKind == SensorKind.Temperature &&
                missingAccess is not null)
            {
                return TelemetryReading.Unavailable(
                    definition.Id,
                    definition.Label,
                    definition.Unit,
                    ReadingStatus.PermissionRequired,
                    missingAccess);
            }

            var selected = SensorSelector.Select(
                candidates,
                definition.HardwareKind,
                definition.SensorKind,
                definition.PreferredNames);
            if (selected is not null)
            {
                return TelemetryReading.Available(
                    definition.Id,
                    definition.Label,
                    selected.Value!.Value,
                    definition.Unit,
                    selected.Source);
            }

            var onlyImplausible = candidates.Any(candidate =>
                candidate.HardwareKind == definition.HardwareKind &&
                candidate.SensorKind == definition.SensorKind &&
                candidate.Value.HasValue &&
                definition.PreferredNames.Contains(candidate.Name, StringComparer.OrdinalIgnoreCase));
            return TelemetryReading.Unavailable(
                definition.Id,
                definition.Label,
                definition.Unit,
                ReadingStatus.Unavailable,
                onlyImplausible ? "sensor_implausible" : "sensor_not_found");
        });
    }

    private string? MissingTemperatureAccess()
    {
        SensorAccess access;
        try
        {
            access = accessProbe.Probe();
        }
        catch
        {
            return "sensor_permission_required";
        }

        if (!access.HasSensorDriver)
        {
            return "sensor_driver_missing";
        }

        return access.IsElevated ? null : "sensor_elevation_required";
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
