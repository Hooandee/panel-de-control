using PanelDeControl.Core.Capabilities;

namespace PanelDeControl.Hardware.Capabilities;

public interface ICapabilityProbe
{
    string Id { get; }

    CapabilityStatus Probe();
}

public sealed class WmiClassCapabilityProbe : ICapabilityProbe
{
    private readonly IWmiClassCatalog catalog;
    private readonly string wmiNamespace;
    private readonly string className;

    public WmiClassCapabilityProbe(string id, IWmiClassCatalog catalog, string wmiNamespace, string className)
    {
        Id = id;
        this.catalog = catalog;
        this.wmiNamespace = wmiNamespace;
        this.className = className;
    }

    public string Id { get; }

    public CapabilityStatus Probe()
    {
        return catalog.HasClass(wmiNamespace, className) ? CapabilityStatus.Present : CapabilityStatus.Absent;
    }
}

public sealed class DevicePathCapabilityProbe : ICapabilityProbe
{
    private readonly IDevicePathProbe devices;
    private readonly IReadOnlyList<string> paths;

    public DevicePathCapabilityProbe(string id, IDevicePathProbe devices, params string[] paths)
    {
        Id = id;
        this.devices = devices;
        this.paths = paths;
    }

    public string Id { get; }

    public CapabilityStatus Probe()
    {
        return paths.Any(devices.Exists) ? CapabilityStatus.Present : CapabilityStatus.Absent;
    }
}

public sealed class SensorDriverCapabilityProbe : ICapabilityProbe
{
    private readonly ISensorAccessProbe access;

    public SensorDriverCapabilityProbe(ISensorAccessProbe access)
    {
        this.access = access;
    }

    public string Id => CapabilityIds.SensorDriver;

    public CapabilityStatus Probe()
    {
        var result = access.Probe();
        if (!result.HasSensorDriver)
        {
            return CapabilityStatus.Absent;
        }

        return result.IsElevated ? CapabilityStatus.Present : CapabilityStatus.PermissionRequired;
    }
}

public sealed class RunningSoftwareCapabilityProbe : ICapabilityProbe
{
    private readonly ISoftwareInventory software;
    private readonly IReadOnlyList<string> serviceNames;
    private readonly IReadOnlyList<string> processNames;

    public RunningSoftwareCapabilityProbe(
        string id,
        ISoftwareInventory software,
        IReadOnlyList<string> serviceNames,
        IReadOnlyList<string> processNames)
    {
        Id = id;
        this.software = software;
        this.serviceNames = serviceNames;
        this.processNames = processNames;
    }

    public string Id { get; }

    public CapabilityStatus Probe()
    {
        var running = serviceNames.Any(software.IsServiceRunning) ||
            processNames.Any(software.IsProcessRunning);
        return running ? CapabilityStatus.Present : CapabilityStatus.Absent;
    }
}
