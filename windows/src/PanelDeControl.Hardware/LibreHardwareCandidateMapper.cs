using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public sealed record LibreSensorReading(
    string Identifier,
    string HardwareType,
    string SensorType,
    string Name,
    double? Value);

public static class LibreHardwareCandidateMapper
{
    public static IReadOnlyList<SensorCandidate> Map(
        IEnumerable<LibreSensorReading> readings)
    {
        if (readings is null)
        {
            throw new ArgumentNullException(nameof(readings));
        }

        return readings
            .Select(Map)
            .Where(candidate => candidate is not null)
            .Cast<SensorCandidate>()
            .ToArray();
    }

    private static SensorCandidate? Map(LibreSensorReading reading)
    {
        var hardwareKind = reading.HardwareType switch
        {
            "Cpu" => HardwareKind.Cpu,
            "GpuAmd" or "GpuIntel" or "GpuNvidia" => HardwareKind.Gpu,
            "Battery" => HardwareKind.Battery,
            "Memory" => HardwareKind.Memory,
            _ => HardwareKind.Unknown,
        };
        var sensorKind = reading.SensorType switch
        {
            "Temperature" => SensorKind.Temperature,
            "Load" => SensorKind.Load,
            "Level" => SensorKind.Level,
            "Power" => SensorKind.Power,
            "Fan" => SensorKind.Fan,
            _ => SensorKind.Unknown,
        };

        if (hardwareKind == HardwareKind.Unknown || sensorKind == SensorKind.Unknown)
        {
            return null;
        }

        return new SensorCandidate(
            reading.Identifier,
            hardwareKind,
            sensorKind,
            reading.Name,
            reading.Value,
            $"librehardwaremonitor/{reading.Identifier}");
    }
}
