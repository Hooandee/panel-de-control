using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using PanelDeControl.Hardware;

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

        var collector = new SnapshotCollector(
            new SystemClock(),
            new DeviceIdentityReader(DeviceCatalogResource.TryLoad()),
            new LibreHardwareReader(),
            new PowerStatusReader(),
            new WindowsSensorAccessProbe());
        var server = new SnapshotPipeServer(
            ServicePipeSecurity.PipeName,
            collector,
            ServicePipeSecurity.Create);

        Host.CreateDefaultBuilder(args)
            .UseWindowsService(options => options.ServiceName = ServiceName)
            .ConfigureServices(services => services.AddHostedService(
                _ => new SnapshotServiceWorker(server)))
            .Build()
            .Run();
        return 0;
    }
}
