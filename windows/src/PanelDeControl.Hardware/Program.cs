namespace PanelDeControl.Hardware;

public static class Program
{
    public static async Task<int> Main()
    {
        if (!OperatingSystem.IsWindows())
        {
            return 1;
        }
        try
        {
            // Process teardown owns cleanup because a timed-out hardware poll may still be active.
            var clock = new SystemClock();
            var localCollector = new SnapshotCollector(
                clock,
                new DeviceIdentityReader(DeviceCatalogResource.TryLoad()),
                new LibreHardwareReader(),
                new PowerStatusReader(),
                new WindowsSensorAccessProbe());
            var serviceClient = new ServiceSnapshotClient();
            var collector = new ServiceBackedSnapshotProvider(
                localCollector,
                serviceClient,
                clock);
            var snapshotServer = new SnapshotPipeServer(
                SnapshotPipeServer.PackagedPipeName,
                collector,
                PackageNamedPipeServerFactory.Create,
                inventoryProvider: new ServiceInventoryProvider(serviceClient, clock));
            var volumeController = new CoreAudioVolumeController(
                new CoreAudioEndpointVolumeProvider());
            var volumeServer = new VolumeControlPipeServer(
                VolumeControlPipeServer.PackagedPipeName,
                volumeController,
                PackageNamedPipeServerFactory.CreateControl);
            var brightnessController = new IntegratedDisplayBrightnessController(
                new WmiDisplayBrightnessProvider());
            var brightnessServer = new BrightnessControlPipeServer(
                BrightnessControlPipeServer.PackagedPipeName,
                brightnessController,
                PackageNamedPipeServerFactory.CreateControl);
            var refreshServer = new RefreshRatePipeServer(
                RefreshRatePipeServer.PackagedPipeName,
                new RefreshRateController(new PrimaryDisplayModeProvider()),
                PackageNamedPipeServerFactory.CreateControl);
            var tdpServer = new TdpControlPipeServer(
                TdpControlPipeServer.PackagedPipeName,
                new ServiceTdpClient(),
                new PackagedWidgetClientValidator(),
                PackageNamedPipeServerFactory.CreateControl);

            using var brokerLifetime = new CancellationTokenSource();
            var snapshotTask = snapshotServer.RunAsync(brokerLifetime.Token);
            var volumeTask = volumeServer.RunUntilCancelledAsync(
                brokerLifetime.Token);
            var brightnessTask = brightnessServer.RunUntilCancelledAsync(
                brokerLifetime.Token);
            var tdpTask = tdpServer.RunUntilCancelledAsync(
                brokerLifetime.Token);
            var refreshTask = refreshServer.RunUntilCancelledAsync(
                brokerLifetime.Token);
            try
            {
                var completedTask = await Task
                    .WhenAny(snapshotTask, volumeTask, brightnessTask, tdpTask, refreshTask)
                    .ConfigureAwait(false);
                await completedTask.ConfigureAwait(false);
            }
            finally
            {
                brokerLifetime.Cancel();
                await Task
                    .WhenAll(snapshotTask, volumeTask, brightnessTask, tdpTask, refreshTask)
                    .ConfigureAwait(false);
            }
            return 0;
        }
        catch (Exception exception)
        {
            CompanionLog.Write("fatal", exception);
            return 1;
        }
    }
}
