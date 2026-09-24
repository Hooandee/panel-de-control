namespace PanelDeControl.Hardware;

public sealed record WmiMonitorConnection(
    string InstanceName,
    bool Active,
    uint VideoOutputTechnology);

public sealed record WmiMonitorBrightnessReading(
    string InstanceName,
    bool Active,
    int CurrentBrightness,
    IReadOnlyList<int> Levels);

public sealed record WmiMonitorBrightnessMethod(
    string InstanceName,
    bool Active);

public static class WmiDisplayBrightnessCapabilityMapper
{
    public static IReadOnlyList<DisplayBrightnessCapability> Map(
        IEnumerable<WmiMonitorConnection> connections,
        IEnumerable<WmiMonitorBrightnessReading> readings,
        IEnumerable<WmiMonitorBrightnessMethod> methods)
    {
        if (connections is null)
        {
            throw new ArgumentNullException(nameof(connections));
        }

        if (readings is null)
        {
            throw new ArgumentNullException(nameof(readings));
        }

        if (methods is null)
        {
            throw new ArgumentNullException(nameof(methods));
        }

        var activeReadings = readings
            .Where(reading => reading.Active)
            .ToArray();
        var writableInstances = new HashSet<string>(
            methods
                .Where(method => method.Active)
                .Select(method => method.InstanceName),
            StringComparer.OrdinalIgnoreCase);

        return connections
            .Where(connection => connection.Active)
            .SelectMany(
                connection => activeReadings
                    .Where(
                        reading => string.Equals(
                            connection.InstanceName,
                            reading.InstanceName,
                            StringComparison.OrdinalIgnoreCase))
                    .Select(
                        reading => new DisplayBrightnessCapability(
                            connection.InstanceName,
                            true,
                            connection.VideoOutputTechnology,
                            reading.CurrentBrightness,
                            reading.Levels,
                            writableInstances.Contains(connection.InstanceName))))
            .ToArray();
    }
}
