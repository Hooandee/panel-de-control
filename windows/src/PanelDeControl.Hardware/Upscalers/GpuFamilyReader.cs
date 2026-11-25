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
        var names = new List<string?>();
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

            using (var adapters = new ManagementObjectSearcher("SELECT Name, PNPDeviceID FROM Win32_VideoController"))
            using (var results = adapters.Get())
            {
                foreach (ManagementObject adapter in results)
                {
                    if (GpuFamily.FromPnpId(Convert.ToString(adapter["PNPDeviceID"])) is { } gpu)
                    {
                        gpus.Add(gpu);
                        names.Add(Convert.ToString(adapter["Name"])?.Trim());
                    }
                }
            }
        }
        catch (Exception exception) when (exception is ManagementException or COMException or UnauthorizedAccessException)
        {
        }

        var result = rules.DetectDiscrete(GpuFamily.CpuVendor(manufacturer), name, gpus);
        var chosen = rules.ChosenAdapter(gpus);
        var adapterName = chosen >= 0 ? names[chosen] : names.FirstOrDefault(entry => !string.IsNullOrEmpty(entry));
        return new GpuFamilyResult(result.Generation, result.Source, string.IsNullOrEmpty(adapterName) ? null : adapterName);
    }
}
