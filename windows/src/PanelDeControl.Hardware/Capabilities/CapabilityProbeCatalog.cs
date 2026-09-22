using PanelDeControl.Core.Devices;

namespace PanelDeControl.Hardware.Capabilities;

public sealed class CapabilityProbeCatalog
{
    private const string WmiNamespace = @"root\WMI";

    private readonly IWmiClassCatalog wmi;
    private readonly IDevicePathProbe devices;
    private readonly ISoftwareInventory software;
    private readonly ISensorAccessProbe sensorAccess;

    public CapabilityProbeCatalog(
        IWmiClassCatalog wmi,
        IDevicePathProbe devices,
        ISoftwareInventory software,
        ISensorAccessProbe sensorAccess)
    {
        this.wmi = wmi;
        this.devices = devices;
        this.software = software;
        this.sensorAccess = sensorAccess;
    }

    public IReadOnlyList<ICapabilityProbe> For(DeviceProfile? profile)
    {
        var probes = new List<ICapabilityProbe> { new SensorDriverCapabilityProbe(sensorAccess) };
        var key = profile?.Key ?? string.Empty;
        if (key.StartsWith("rog_", StringComparison.Ordinal))
        {
            probes.Add(new DevicePathCapabilityProbe(CapabilityIds.AsusAtkAcpi, devices, @"\\.\ATKACPI"));
            probes.Add(Rival(
                CapabilityIds.RivalArmouryCrate,
                new[] { "ArmouryCrateSEService", "AsusAppService", "ArmouryCrateControlInterface" },
                Array.Empty<string>()));
        }
        else if (key.StartsWith("legion_", StringComparison.Ordinal))
        {
            probes.Add(new WmiClassCapabilityProbe(CapabilityIds.LenovoGameZone, wmi, WmiNamespace, "LENOVO_GAMEZONE_DATA"));
            probes.Add(new WmiClassCapabilityProbe(CapabilityIds.LenovoOtherMethod, wmi, WmiNamespace, "LENOVO_OTHER_METHOD"));
            probes.Add(new WmiClassCapabilityProbe(CapabilityIds.LenovoFanMethod, wmi, WmiNamespace, "LENOVO_FAN_METHOD"));
            probes.Add(Rival(
                CapabilityIds.RivalLegionSpace,
                new[] { "DAService" },
                new[] { "LegionSpace", "LSDaemon", "LegionGoQuickSettings" }));
        }
        else if (key.StartsWith("msi_claw", StringComparison.Ordinal))
        {
            probes.Add(new WmiClassCapabilityProbe(CapabilityIds.MsiAcpi, wmi, WmiNamespace, "MSI_ACPI"));
            probes.Add(Rival(
                CapabilityIds.RivalMsiCenter,
                new[] { "MSI Foundation Service" },
                new[] { "MSI_Center_M_Server", "MSI Center M", "MCMOSDInfo" }));
            if (string.Equals(profile?.Vendor, "intel", StringComparison.Ordinal))
            {
                probes.Add(Rival(CapabilityIds.RivalIntelThermal, new[] { "dptftcs", "ipfsvc" }, Array.Empty<string>()));
            }
        }

        return probes;
    }

    private RunningSoftwareCapabilityProbe Rival(string id, string[] services, string[] processes)
    {
        return new RunningSoftwareCapabilityProbe(id, software, services, processes);
    }
}
