using System.Management;
using System.Runtime.Versioning;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Reports;

/// <summary>
/// What a report needs to know about the machine to build for it: firmware, processor, graphics,
/// battery, power plans, drivers and every vendor WMI class or service a power or fan path could use.
/// Each part is read on its own, so one blocked query only marks that part.
/// </summary>
[SupportedOSPlatform("windows")]
public static class MachineInventory
{
    private const int MaximumDrivers = 600;
    private const int MaximumWmiClasses = 400;
    private static readonly TimeSpan QueryTimeout = TimeSpan.FromSeconds(8);

    // Services and drivers that own or block a power, fan or sensor path on handhelds.
    private static readonly Regex VendorService = new(
        @"asus|armoury|rog|atk|lenovo|legion|msi|claw|gpd|ayaneo|aya|onexplayer|oxp|zotac|amd|ryzen|pawnio|winring|inpout|libre|hwinfo|throttlestop|handheld",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex SystemWmiClass = new(
        @"^(?:__|CIM_|Win32_|MS|Msft|Wmi|Kernel|Ntms|RegistryKey|SystemConfiguration|Event|PowerMeter|NDIS)",
        RegexOptions.CultureInvariant);

    public static JsonObject Collect()
    {
        return new JsonObject
        {
            ["system"] = Part(ReadSystem),
            ["bios"] = Part(ReadBios),
            ["board"] = Part(() => First("SELECT Manufacturer, Product FROM Win32_BaseBoard", "manufacturer:Manufacturer", "product:Product")),
            ["os"] = Part(() => First(
                "SELECT Caption, Version, BuildNumber, OSArchitecture FROM Win32_OperatingSystem",
                "caption:Caption", "version:Version", "build:BuildNumber", "architecture:OSArchitecture")),
            ["processors"] = Part(() => All(
                "SELECT Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, CurrentClockSpeed FROM Win32_Processor",
                "name:Name", "manufacturer:Manufacturer", "cores:NumberOfCores", "threads:NumberOfLogicalProcessors",
                "max_clock_mhz:MaxClockSpeed", "current_clock_mhz:CurrentClockSpeed")),
            ["gpus"] = Part(() => All(
                "SELECT Name, VideoProcessor, DriverVersion, DriverDate, AdapterRAM, CurrentRefreshRate, CurrentHorizontalResolution, CurrentVerticalResolution FROM Win32_VideoController",
                "name:Name", "video_processor:VideoProcessor", "driver_version:DriverVersion", "driver_date:DriverDate",
                "adapter_ram:AdapterRAM", "refresh_hz:CurrentRefreshRate", "width:CurrentHorizontalResolution", "height:CurrentVerticalResolution")),
            ["batteries"] = Part(() => All(
                "SELECT Name, Chemistry, DesignVoltage, EstimatedChargeRemaining, BatteryStatus FROM Win32_Battery",
                "name:Name", "chemistry:Chemistry", "design_voltage_mv:DesignVoltage", "charge_percent:EstimatedChargeRemaining", "status:BatteryStatus")),
            ["battery_capacity"] = Part(ReadBatteryCapacity),
            ["power_plans"] = Part(() => AllIn(
                @"root\cimv2\power", "SELECT ElementName, IsActive FROM Win32_PowerPlan",
                "name:ElementName", "active:IsActive")),
            ["drivers"] = Part(ReadDrivers),
            ["vendor_wmi_classes"] = Part(ReadVendorWmiClasses),
            ["vendor_services"] = Part(ReadVendorServices),
        };
    }

    private static JsonNode? Part(Func<JsonNode?> read)
    {
        try
        {
            return read();
        }
        catch (Exception exception)
        {
            return new JsonObject { ["error"] = exception.GetType().Name };
        }
    }

    private static JsonNode? ReadSystem()
    {
        var system = First(
            "SELECT Manufacturer, Model, SystemFamily, SystemSKUNumber, TotalPhysicalMemory FROM Win32_ComputerSystem",
            "manufacturer:Manufacturer", "model:Model", "family:SystemFamily", "sku:SystemSKUNumber", "memory_bytes:TotalPhysicalMemory");
        if (system is JsonObject values)
        {
            values["logical_processors"] = Environment.ProcessorCount;
        }

        return system;
    }

    private static JsonNode? ReadBios()
    {
        return First(
            "SELECT Manufacturer, SMBIOSBIOSVersion, ReleaseDate, EmbeddedControllerMajorVersion, EmbeddedControllerMinorVersion, SMBIOSMajorVersion, SMBIOSMinorVersion FROM Win32_BIOS",
            "vendor:Manufacturer", "bios_version:SMBIOSBIOSVersion", "bios_date:ReleaseDate",
            "ec_major:EmbeddedControllerMajorVersion", "ec_minor:EmbeddedControllerMinorVersion",
            "smbios_major:SMBIOSMajorVersion", "smbios_minor:SMBIOSMinorVersion");
    }

    // These classes live in root\wmi and need the battery driver's consent; a standard user often gets
    // access denied, which the part records instead of guessing a capacity.
    private static JsonNode ReadBatteryCapacity()
    {
        return new JsonObject
        {
            ["design_mwh"] = Part(() => Value("SELECT DesignedCapacity FROM BatteryStaticData", @"root\wmi", "DesignedCapacity")),
            ["full_charge_mwh"] = Part(() => Value("SELECT FullChargedCapacity FROM BatteryFullChargedCapacity", @"root\wmi", "FullChargedCapacity")),
            ["cycle_count"] = Part(() => Value("SELECT CycleCount FROM BatteryCycleCount", @"root\wmi", "CycleCount")),
        };
    }

    private static JsonNode ReadDrivers()
    {
        var drivers = new JsonArray();
        using var searcher = Searcher(
            "SELECT DeviceName, DeviceClass, Manufacturer, DriverProviderName, DriverVersion, DriverDate, InfName, HardWareID FROM Win32_PnPSignedDriver",
            @"root\cimv2");
        using var results = searcher.Get();
        foreach (ManagementObject driver in results)
        {
            using (driver)
            {
                if (driver["DeviceName"] is null)
                {
                    continue;
                }

                if (drivers.Count == MaximumDrivers)
                {
                    break;
                }

                drivers.Add(Pick(driver,
                    "device:DeviceName", "class:DeviceClass", "manufacturer:Manufacturer", "provider:DriverProviderName",
                    "driver_version:DriverVersion", "driver_date:DriverDate", "inf_name:InfName", "hardware_id:HardWareID"));
            }
        }

        return drivers;
    }

    private static JsonNode ReadVendorWmiClasses()
    {
        var names = new List<string>();
        var scope = new ManagementScope(@"root\wmi");
        scope.Connect();
        using var searcher = new ManagementObjectSearcher(
            scope,
            new WqlObjectQuery("SELECT * FROM meta_class"),
            new System.Management.EnumerationOptions { Timeout = QueryTimeout, ReturnImmediately = true });
        using var results = searcher.Get();
        foreach (ManagementClass managementClass in results)
        {
            using (managementClass)
            {
                var name = Convert.ToString(managementClass["__CLASS"]);
                if (!string.IsNullOrEmpty(name) && !SystemWmiClass.IsMatch(name))
                {
                    names.Add(name);
                }
            }
        }

        names.Sort(StringComparer.OrdinalIgnoreCase);
        return new JsonArray(names.Take(MaximumWmiClasses).Select(name => (JsonNode?)JsonValue.Create(name)).ToArray());
    }

    private static JsonNode ReadVendorServices()
    {
        var services = new JsonArray();
        foreach (var service in (JsonArray)All(
                     "SELECT Name, DisplayName, State, StartMode, ServiceType FROM Win32_Service",
                     "name:Name", "display_name:DisplayName", "state:State", "start_mode:StartMode", "type:ServiceType"))
        {
            var name = service?["name"]?.GetValue<string>() ?? string.Empty;
            var displayName = service?["display_name"]?.GetValue<string>() ?? string.Empty;
            if (service is not null && (VendorService.IsMatch(name) || VendorService.IsMatch(displayName)))
            {
                services.Add(service.DeepClone());
            }
        }

        return services;
    }

    private static JsonNode? First(string query, params string[] fields)
    {
        var all = (JsonArray)All(query, fields);
        return all.Count == 0 ? null : all[0]!.DeepClone();
    }

    private static JsonNode All(string query, params string[] fields) => AllIn(@"root\cimv2", query, fields);

    private static JsonNode AllIn(string scope, string query, params string[] fields)
    {
        var rows = new JsonArray();
        using var searcher = Searcher(query, scope);
        using var results = searcher.Get();
        foreach (ManagementObject row in results)
        {
            using (row)
            {
                rows.Add(Pick(row, fields));
            }
        }

        return rows;
    }

    private static JsonNode? Value(string query, string scope, string property)
    {
        using var searcher = Searcher(query, scope);
        using var results = searcher.Get();
        foreach (ManagementObject row in results)
        {
            using (row)
            {
                return ToNode(row[property]);
            }
        }

        return null;
    }

    private static ManagementObjectSearcher Searcher(string query, string scope)
    {
        return new ManagementObjectSearcher(
            new ManagementScope(scope),
            new ObjectQuery(query),
            new System.Management.EnumerationOptions { Timeout = QueryTimeout, ReturnImmediately = true, Rewindable = false });
    }

    // fields are "json_name:WmiProperty".
    private static JsonObject Pick(ManagementBaseObject row, params string[] fields)
    {
        var values = new JsonObject();
        foreach (var field in fields)
        {
            var separator = field.IndexOf(':');
            values[field.Substring(0, separator)] = ToNode(row[field.Substring(separator + 1)]);
        }

        return values;
    }

    private static JsonNode? ToNode(object? value)
    {
        return value switch
        {
            null => null,
            string text => JsonValue.Create(text.Trim()),
            bool flag => JsonValue.Create(flag),
            byte or sbyte or short or ushort or int or uint or long => JsonValue.Create(Convert.ToInt64(value)),
            ulong number => JsonValue.Create(number),
            float or double => JsonValue.Create(Convert.ToDouble(value)),
            string[] texts => new JsonArray(texts.Select(text => (JsonNode?)JsonValue.Create(text)).ToArray()),
            _ => JsonValue.Create(Convert.ToString(value)),
        };
    }
}
