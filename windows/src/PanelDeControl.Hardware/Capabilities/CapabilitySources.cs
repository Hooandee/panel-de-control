namespace PanelDeControl.Hardware.Capabilities;

public interface IWmiClassCatalog
{
    bool HasClass(string wmiNamespace, string className);
}

public interface IDevicePathProbe
{
    bool Exists(string devicePath);
}

public interface ISoftwareInventory
{
    bool IsServiceRunning(string serviceName);

    bool IsProcessRunning(string processName);
}
