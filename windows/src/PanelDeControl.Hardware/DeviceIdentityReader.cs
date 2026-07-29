using System.Management;

namespace PanelDeControl.Hardware;

public sealed class DeviceIdentityReader : IDeviceIdentityReader
{
    public DeviceIdentity Read()
    {
        if (!OperatingSystem.IsWindows())
        {
            return DeviceIdentity.FromDmi(null, null);
        }

        using var searcher = new ManagementObjectSearcher(
            "SELECT Manufacturer, Model FROM Win32_ComputerSystem");
        using var results = searcher.Get();
        foreach (ManagementObject system in results)
        {
            return DeviceIdentity.FromDmi(
                Convert.ToString(system["Manufacturer"]),
                Convert.ToString(system["Model"]));
        }

        return DeviceIdentity.FromDmi(null, null);
    }
}
