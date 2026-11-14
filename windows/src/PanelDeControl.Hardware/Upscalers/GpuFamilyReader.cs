using System.Management;
using System.Runtime.InteropServices;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>The machine's GPU family for upscaler suggestions, from WMI's processor name and display adapters.</summary>
public static class GpuFamilyReader
{
    public static GpuFamilyResult Read(GpuFamily rules)
    {
        if (!OperatingSystem.IsWindows())
        {
            return new GpuFamilyResult("unknown", "unknown");
        }

        string? manufacturer = null;
        string? name = null;
        var gpus = new List<PciGpu>();
        try
        {
            using (var processors = new ManagementObjectSearcher("SELECT Manufacturer, Name FROM Win32_Processor"))
            using (var results = processors.Get())
            {
                foreach (ManagementObject processor in results)
                {
                    manufacturer = Convert.ToString(processor["Manufacturer"]);
                    name = Convert.ToString(processor["Name"])?.Trim();
                    break;
                }
            }

            using (var adapters = new ManagementObjectSearcher("SELECT PNPDeviceID FROM Win32_VideoController"))
            using (var results = adapters.Get())
            {
                foreach (ManagementObject adapter in results)
                {
                    if (GpuFamily.FromPnpId(Convert.ToString(adapter["PNPDeviceID"])) is { } gpu)
                    {
                        gpus.Add(gpu);
                    }
                }
            }
        }
        catch (Exception exception) when (exception is ManagementException or COMException or UnauthorizedAccessException)
        {
        }

        return rules.Detect(GpuFamily.CpuVendor(manufacturer), name, gpus);
    }
}
