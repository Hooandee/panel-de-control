using System.Management;
using System.Runtime.Versioning;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public interface IBatteryHealthSource
{
    IReadOnlyList<TelemetryReading> Read();
}

public sealed class WmiBatteryHealthSource : IBatteryHealthSource
{
    private const string Source = "wmi/root-wmi-battery";
    private static readonly TimeSpan CacheLifetime = TimeSpan.FromMinutes(5);

    private readonly object gate = new();
    private IReadOnlyList<TelemetryReading>? cached;
    private DateTimeOffset cachedAt;

    public IReadOnlyList<TelemetryReading> Read()
    {
        lock (gate)
        {
            var now = DateTimeOffset.UtcNow;
            if (cached is not null && now - cachedAt < CacheLifetime)
            {
                return cached;
            }

            cached = ReadFresh();
            cachedAt = now;
            return cached;
        }
    }

    private static IReadOnlyList<TelemetryReading> ReadFresh()
    {
        if (!OperatingSystem.IsWindows())
        {
            return BatteryHealth.Unavailable(ReadingStatus.Unavailable, "battery_health_windows_only");
        }

        return ReadWindows();
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<TelemetryReading> ReadWindows()
    {
        try
        {
            return BatteryHealth.Map(
                new BatteryHealthSample(
                    ReadFirst("BatteryStaticData", "DesignedCapacity"),
                    ReadFirst("BatteryFullChargedCapacity", "FullChargedCapacity"),
                    ReadFirst("BatteryCycleCount", "CycleCount")),
                Source);
        }
        catch (UnauthorizedAccessException)
        {
            return BatteryHealth.Unavailable(ReadingStatus.PermissionRequired, "battery_health_permission_required");
        }
        catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.AccessDenied)
        {
            return BatteryHealth.Unavailable(ReadingStatus.PermissionRequired, "battery_health_permission_required");
        }
        catch
        {
            return BatteryHealth.Unavailable(ReadingStatus.Fault, "battery_health_failed");
        }
    }

    [SupportedOSPlatform("windows")]
    private static uint? ReadFirst(string className, string property)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(@"root\wmi", $"SELECT {property} FROM {className}");
            foreach (ManagementObject instance in searcher.Get())
            {
                using (instance)
                {
                    return instance[property] is uint value ? value : null;
                }
            }

            return null;
        }
        catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.NotSupported ||
            exception.ErrorCode == ManagementStatus.InvalidClass ||
            exception.ErrorCode == ManagementStatus.NotFound)
        {
            return null;
        }
    }
}
