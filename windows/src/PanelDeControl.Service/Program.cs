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

        // The elevated installer calls this right after it installs the widget package.
        if (args is ["--trust-broker", var brokerDirectory])
        {
            TrustedBrokerStore.Record(Path.Combine(AppContext.BaseDirectory, TrustedBrokerStore.FileName), brokerDirectory);
            Console.WriteLine("trusted " + brokerDirectory);
            return 0;
        }

        var clock = new SystemClock();
        var identityReader = new DeviceIdentityReader(DeviceCatalogResource.TryLoad());
        var sensorAccess = new WindowsSensorAccessProbe();
        var softwareInventory = new WindowsSoftwareInventory();
        var collector = new SnapshotCollector(
            clock,
            identityReader,
            new LibreHardwareReader(),
            new PowerStatusReader(),
            sensorAccess);
        var sensors = new AsusSensorSnapshotProvider(
            collector, identityReader, new AsusAtkSensorTransport(), clock);
        var inventory = new CapabilityInventoryCollector(
            clock,
            identityReader,
            new CapabilityProbeCatalog(
                new WindowsWmiClassCatalog(),
                new WindowsDevicePathProbe(),
                softwareInventory,
                sensorAccess));
        var server = new SnapshotPipeServer(
            ServicePipeSecurity.PipeName,
            sensors,
            ServicePipeSecurity.Create,
            inventoryProvider: inventory);
        var tdpControl = new TdpControlService(
            identityReader,
            new WindowsAcPowerSource(),
            new ArmouryCrateGuard(softwareInventory),
            new AsusAtkTdpTransport());
        var tdpServer = new TdpServicePipeServer(
            TdpServicePipeSecurity.PipeName,
            tdpControl,
            TdpServicePipeSecurity.Create,
            new PackagedTdpClientValidator(TrustedBrokerStore.NextToService()));

        Host.CreateDefaultBuilder(args)
            .UseWindowsService(options => options.ServiceName = ServiceName)
            .ConfigureServices(services =>
            {
                services.AddHostedService(
                    _ => new SnapshotServiceWorker(server));
                services.AddHostedService(
                    _ => new TdpServiceWorker(tdpServer));
                services.AddHostedService(_ => new CompanionLaunchWorker());
            })
            .Build()
            .Run();
        return 0;
    }
}
