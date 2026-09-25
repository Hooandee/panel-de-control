namespace PanelDeControl.Core.Telemetry;

public readonly struct BatteryHealthSample
{
    public BatteryHealthSample(uint? designedCapacity, uint? fullChargedCapacity, uint? cycleCount)
    {
        DesignedCapacity = designedCapacity;
        FullChargedCapacity = fullChargedCapacity;
        CycleCount = cycleCount;
    }

    public uint? DesignedCapacity { get; }

    public uint? FullChargedCapacity { get; }

    public uint? CycleCount { get; }
}

public static class BatteryHealth
{
    public const string DesignCapacityId = "battery.design_capacity";
    public const string FullCapacityId = "battery.full_capacity";
    public const string HealthId = "battery.health";
    public const string CyclesId = "battery.cycles";

    public static IReadOnlyList<TelemetryReading> Map(BatteryHealthSample sample, string source)
    {
        var design = Plausible(SensorKind.Capacity, sample.DesignedCapacity);
        var full = Plausible(SensorKind.Capacity, sample.FullChargedCapacity);
        var health = design is double designed && full is double charged
            ? Plausible(SensorKind.Health, Math.Round(charged / designed * 100))
            : null;
        return new[]
        {
            Reading(DesignCapacityId, "Capacidad de diseño", design, "mWh", source),
            Reading(FullCapacityId, "Capacidad actual", full, "mWh", source),
            Reading(HealthId, "Salud", health, "%", source),
            Reading(CyclesId, "Ciclos", Plausible(SensorKind.Cycles, sample.CycleCount), "cycles", source),
        };
    }

    public static IReadOnlyList<TelemetryReading> Unavailable(ReadingStatus status, string errorCode)
    {
        return new[]
        {
            TelemetryReading.Unavailable(DesignCapacityId, "Capacidad de diseño", "mWh", status, errorCode),
            TelemetryReading.Unavailable(FullCapacityId, "Capacidad actual", "mWh", status, errorCode),
            TelemetryReading.Unavailable(HealthId, "Salud", "%", status, errorCode),
            TelemetryReading.Unavailable(CyclesId, "Ciclos", "cycles", status, errorCode),
        };
    }

    public static SensorKind KindOf(string id)
    {
        return id switch
        {
            DesignCapacityId or FullCapacityId => SensorKind.Capacity,
            HealthId => SensorKind.Health,
            CyclesId => SensorKind.Cycles,
            _ => SensorKind.Unknown,
        };
    }

    private static double? Plausible(SensorKind kind, double? value)
    {
        return SensorPlausibility.IsPlausible(kind, value) ? value : null;
    }

    private static TelemetryReading Reading(string id, string label, double? value, string unit, string source)
    {
        return value is double available
            ? TelemetryReading.Available(id, label, available, unit, source)
            : TelemetryReading.Unavailable(id, label, unit, ReadingStatus.Unavailable, "battery_health_unreported");
    }
}
