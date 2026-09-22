using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Capabilities;

namespace PanelDeControl.Service;

public static class Program
{
    public const string ServiceName = "PanelDeControlService";

    public static int Main(string[] args)
    {
        if (!OperatingSystem.IsWindows())
        {
            return 1;
        }

        var clock = new SystemClock();
        var identityReader = new DeviceIdentityReader(DeviceCatalogResource.TryLoad());
        var sensorAccess = new WindowsSensorAccessProbe();
        var collector = new SnapshotCollector(
            clock,
            identityReader,
            new LibreHardwareReader(),
            new PowerStatusReader(),
            sensorAccess);
        var inventory = new CapabilityInventoryCollector(
            clock,
            identityReader,
            new CapabilityProbeCatalog(
                new WindowsWmiClassCatalog(),
                new WindowsDevicePathProbe(),
                new WindowsSoftwareInventory(),
                sensorAccess));
        var server = new SnapshotPipeServer(
            ServicePipeSecurity.PipeName,
            collector,
            ServicePipeSecurity.Create,
            inventoryProvider: inventory);

        Host.CreateDefaultBuilder(args)
            .UseWindowsService(options => options.ServiceName = ServiceName)
            .ConfigureServices(services => services.AddHostedService(
                _ => new SnapshotServiceWorker(server)))
            .Build()
            .Run();
        return 0;
    }
}
