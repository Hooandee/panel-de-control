using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace PanelDeControl.Hardware.Capabilities;

public sealed class WindowsWmiClassCatalog : IWmiClassCatalog
{
    public bool HasClass(string wmiNamespace, string className)
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }

        try
        {
            using var wmiClass = new ManagementClass(wmiNamespace, className, null);
            wmiClass.Get();
            return true;
        }
        catch (ManagementException exception) when (
            exception.ErrorCode is ManagementStatus.NotFound or ManagementStatus.InvalidClass or ManagementStatus.InvalidNamespace)
        {
            return false;
        }
        catch (ManagementException exception) when (exception.ErrorCode == ManagementStatus.AccessDenied)
        {
            throw new UnauthorizedAccessException(exception.Message, exception);
        }
    }
}

public sealed class WindowsDevicePathProbe : IDevicePathProbe
{
    private const uint FileShareReadWrite = 0x00000003;
    private const uint OpenExisting = 3;

    // Desired access 0 only queries the device object; it never sends an IOCTL or reads data.
    public bool Exists(string devicePath)
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }

        using var handle = CreateFile(devicePath, 0, FileShareReadWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        return !handle.IsInvalid;
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);
}

public sealed class WindowsSoftwareInventory : ISoftwareInventory
{
    public bool IsServiceRunning(string serviceName)
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }

        using var searcher = new ManagementObjectSearcher(
            "SELECT State FROM Win32_Service WHERE Name = '" + serviceName.Replace("'", "''") + "'");
        using var results = searcher.Get();
        foreach (ManagementObject service in results)
        {
            if (string.Equals(Convert.ToString(service["State"]), "Running", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    public bool IsProcessRunning(string processName)
    {
        var processes = Process.GetProcessesByName(processName);
        try
        {
            return processes.Length > 0;
        }
        finally
        {
            foreach (var process in processes)
            {
                process.Dispose();
            }
        }
    }
}
