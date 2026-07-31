using System.Management;
using System.Runtime.Versioning;

namespace PanelDeControl.Hardware;

public sealed class WmiDisplayBrightnessProvider : IDisplayBrightnessProvider
{
    private const string NamespacePath = @"\\.\root\wmi";
    private static readonly TimeSpan WmiTimeout = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan OperationTimeout =
        TimeSpan.FromMilliseconds(1500);

    public IReadOnlyList<DisplayBrightnessCapability> Discover()
    {
        if (!OperatingSystem.IsWindows())
        {
            throw CreatePlatformException();
        }

        return RunBounded(DiscoverWindows);
    }

    public uint SetBrightness(
        string instanceName,
        int percentage,
        uint timeoutSeconds)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw CreatePlatformException();
        }

        if (string.IsNullOrWhiteSpace(instanceName))
        {
            throw new ArgumentException(
                "Instance name must not be empty.",
                nameof(instanceName));
        }

        if (percentage < 0 || percentage > 100)
        {
            throw new ArgumentOutOfRangeException(nameof(percentage));
        }

        if (timeoutSeconds == 0)
        {
            throw new ArgumentOutOfRangeException(nameof(timeoutSeconds));
        }

        return SetBrightnessBoundedWindows(
            instanceName,
            percentage,
            timeoutSeconds);
    }

    public int ReadBrightness(string instanceName)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw CreatePlatformException();
        }

        if (string.IsNullOrWhiteSpace(instanceName))
        {
            throw new ArgumentException(
                "Instance name must not be empty.",
                nameof(instanceName));
        }

        return ReadBrightnessBoundedWindows(instanceName);
    }

    [SupportedOSPlatform("windows")]
    private static uint SetBrightnessBoundedWindows(
        string instanceName,
        int percentage,
        uint timeoutSeconds)
    {
        return RunBounded(
            () => SetBrightnessWindows(
                instanceName,
                percentage,
                timeoutSeconds));
    }

    [SupportedOSPlatform("windows")]
    private static int ReadBrightnessBoundedWindows(string instanceName)
    {
        return RunBounded(() => ReadBrightnessWindows(instanceName));
    }

    [SupportedOSPlatform("windows")]
    private static T RunBounded<T>(Func<T> operation)
    {
        try
        {
            return Task
                .Run(operation)
                .WaitAsync(OperationTimeout)
                .GetAwaiter()
                .GetResult();
        }
        catch (ManagementException exception)
            when (exception.ErrorCode == ManagementStatus.AccessDenied)
        {
            throw new UnauthorizedAccessException(
                "Windows denied access to display brightness WMI.",
                exception);
        }
        catch (ManagementException exception)
            when (exception.ErrorCode == ManagementStatus.Timedout)
        {
            throw new TimeoutException(
                "Display brightness WMI timed out.",
                exception);
        }
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<DisplayBrightnessCapability> DiscoverWindows()
    {
        var connections = QueryConnections();
        var readings = QueryBrightnessReadings();
        var methods = QueryBrightnessMethods();
        return WmiDisplayBrightnessCapabilityMapper.Map(
            connections,
            readings,
            methods);
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<WmiMonitorConnection> QueryConnections()
    {
        return Query(
            "SELECT Active, InstanceName, VideoOutputTechnology " +
            "FROM WmiMonitorConnectionParams WHERE Active = TRUE",
            item => new WmiMonitorConnection(
                ReadString(item, "InstanceName"),
                ReadBoolean(item, "Active"),
                Convert.ToUInt32(item["VideoOutputTechnology"])));
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<WmiMonitorBrightnessReading>
        QueryBrightnessReadings()
    {
        return Query(
            "SELECT Active, CurrentBrightness, InstanceName, Level, Levels " +
            "FROM WmiMonitorBrightness WHERE Active = TRUE",
            item => new WmiMonitorBrightnessReading(
                ReadString(item, "InstanceName"),
                ReadBoolean(item, "Active"),
                Convert.ToInt32(item["CurrentBrightness"]),
                ReadLevels(item["Level"])));
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<WmiMonitorBrightnessMethod>
        QueryBrightnessMethods()
    {
        return Query(
            "SELECT Active, InstanceName " +
            "FROM WmiMonitorBrightnessMethods WHERE Active = TRUE",
            item => new WmiMonitorBrightnessMethod(
                ReadString(item, "InstanceName"),
                ReadBoolean(item, "Active")));
    }

    [SupportedOSPlatform("windows")]
    private static int ReadBrightnessWindows(string instanceName)
    {
        var matches = QueryBrightnessReadings()
            .Where(
                reading => string.Equals(
                    reading.InstanceName,
                    instanceName,
                    StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidOperationException(
                "The integrated display brightness readback is unavailable.");
        }

        return matches[0].CurrentBrightness;
    }

    [SupportedOSPlatform("windows")]
    private static uint SetBrightnessWindows(
        string instanceName,
        int percentage,
        uint timeoutSeconds)
    {
        using var searcher = CreateSearcher(
            "SELECT Active, InstanceName " +
            "FROM WmiMonitorBrightnessMethods WHERE Active = TRUE");
        using var collection = searcher.Get();
        var matches = new List<ManagementObject>();
        try
        {
            foreach (ManagementObject item in collection)
            {
                if (string.Equals(
                    ReadString(item, "InstanceName"),
                    instanceName,
                    StringComparison.OrdinalIgnoreCase))
                {
                    matches.Add(item);
                }
                else
                {
                    item.Dispose();
                }
            }

            if (matches.Count != 1)
            {
                throw new InvalidOperationException(
                    "The integrated display brightness method is unavailable.");
            }

            using var parameters = matches[0]
                .GetMethodParameters("WmiSetBrightness");
            parameters["Timeout"] = timeoutSeconds;
            parameters["Brightness"] = (byte)percentage;
            using var result = matches[0].InvokeMethod(
                "WmiSetBrightness",
                parameters,
                new InvokeMethodOptions { Timeout = WmiTimeout });
            if (result is null || result["ReturnValue"] is null)
            {
                throw new InvalidOperationException(
                    "WmiSetBrightness did not return a status code.");
            }

            return Convert.ToUInt32(result["ReturnValue"]);
        }
        finally
        {
            foreach (var match in matches)
            {
                match.Dispose();
            }
        }
    }

    [SupportedOSPlatform("windows")]
    private static IReadOnlyList<T> Query<T>(
        string query,
        Func<ManagementBaseObject, T> map)
    {
        using var searcher = CreateSearcher(query);
        using var collection = searcher.Get();
        var values = new List<T>();
        foreach (ManagementObject item in collection)
        {
            using (item)
            {
                values.Add(map(item));
            }
        }

        return values;
    }

    [SupportedOSPlatform("windows")]
    private static ManagementObjectSearcher CreateSearcher(string query)
    {
        var scope = new ManagementScope(
            NamespacePath,
            new ConnectionOptions { Timeout = WmiTimeout });
        return new ManagementObjectSearcher(
            scope,
            new ObjectQuery(query),
            new System.Management.EnumerationOptions
            {
                Timeout = WmiTimeout,
                Rewindable = false,
            });
    }

    private static IReadOnlyList<int> ReadLevels(object? value)
    {
        if (value is not Array levels)
        {
            return Array.Empty<int>();
        }

        return levels
            .Cast<object>()
            .Select(Convert.ToInt32)
            .ToArray();
    }

    [SupportedOSPlatform("windows")]
    private static string ReadString(
        ManagementBaseObject item,
        string propertyName)
    {
        return item[propertyName] as string ?? string.Empty;
    }

    [SupportedOSPlatform("windows")]
    private static bool ReadBoolean(
        ManagementBaseObject item,
        string propertyName)
    {
        return item[propertyName] is bool value && value;
    }

    private static PlatformNotSupportedException CreatePlatformException()
    {
        return new PlatformNotSupportedException(
            "Display brightness WMI is only available on Windows.");
    }
}
