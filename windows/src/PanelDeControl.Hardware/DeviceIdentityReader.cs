using System.Management;
using PanelDeControl.Core.Devices;

namespace PanelDeControl.Hardware;

public sealed class DeviceIdentityReader : IDeviceIdentityReader
{
    private readonly DeviceCatalog? catalog;

    public DeviceIdentityReader(DeviceCatalog? catalog)
    {
        this.catalog = catalog;
    }

    public DeviceIdentity Read()
    {
        if (!OperatingSystem.IsWindows())
        {
            return DeviceIdentity.Unrecognized();
        }

        string? manufacturer = null;
        string? model = null;
        using (var systems = new ManagementObjectSearcher(
                   "SELECT Manufacturer, Model FROM Win32_ComputerSystem"))
        using (var results = systems.Get())
        {
            foreach (ManagementObject system in results)
            {
                manufacturer = Convert.ToString(system["Manufacturer"]);
                model = Convert.ToString(system["Model"]);
                break;
            }
        }

        return DeviceIdentity.FromDmi(catalog, manufacturer, model, ReadBoardProduct());
    }

    private static string? ReadBoardProduct()
    {
        if (!OperatingSystem.IsWindows())
        {
            return null;
        }

        try
        {
            using var boards = new ManagementObjectSearcher("SELECT Product FROM Win32_BaseBoard");
            using var results = boards.Get();
            foreach (ManagementObject board in results)
            {
                return Convert.ToString(board["Product"]);
            }
        }
        catch (ManagementException)
        {
        }

        return null;
    }
}
