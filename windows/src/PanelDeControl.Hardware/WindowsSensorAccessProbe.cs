using System.Security.Principal;
using Microsoft.Win32;

namespace PanelDeControl.Hardware;

public sealed class WindowsSensorAccessProbe : ISensorAccessProbe
{
    // LibreHardwareMonitor detects PawnIO through this uninstall entry; without the driver its
    // ring0 reads return zeroed buffers instead of failing.
    private const string PawnIoUninstallKey =
        @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO";

    public SensorAccess Probe()
    {
        if (!OperatingSystem.IsWindows())
        {
            return new SensorAccess(false, false);
        }

        using var identity = WindowsIdentity.GetCurrent();
        var isElevated = new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        return new SensorAccess(isElevated, HasPawnIo(RegistryView.Registry64) || HasPawnIo(RegistryView.Registry32));
    }

    private static bool HasPawnIo(RegistryView view)
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }

        using var root = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
        using var key = root.OpenSubKey(PawnIoUninstallKey);
        return Version.TryParse(key?.GetValue("DisplayVersion") as string, out _);
    }
}
