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
            var collector = new SnapshotCollector(
                new SystemClock(),
                new DeviceIdentityReader(),
                new LibreHardwareReader(),
                new PowerStatusReader());
            var snapshotServer = new SnapshotPipeServer(
                SnapshotPipeServer.PackagedPipeName,
                collector,
                PackageNamedPipeServerFactory.Create);
            var volumeController = new CoreAudioVolumeController(
                new CoreAudioEndpointVolumeProvider());
            var volumeServer = new VolumeControlPipeServer(
                VolumeControlPipeServer.PackagedPipeName,
                volumeController,
                PackageNamedPipeServerFactory.CreateControl);

            using var brokerLifetime = new CancellationTokenSource();
            var snapshotTask = snapshotServer.RunAsync(brokerLifetime.Token);
            var volumeTask = volumeServer.RunUntilCancelledAsync(
                brokerLifetime.Token);
            try
            {
                var completedTask = await Task
                    .WhenAny(snapshotTask, volumeTask)
                    .ConfigureAwait(false);
                await completedTask.ConfigureAwait(false);
            }
            finally
            {
                brokerLifetime.Cancel();
                await Task
                    .WhenAll(snapshotTask, volumeTask)
                    .ConfigureAwait(false);
            }

            return 0;
        }
        catch
        {
            return 1;
        }
    }
}
