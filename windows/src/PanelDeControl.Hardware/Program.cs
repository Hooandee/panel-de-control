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
            var server = new SnapshotPipeServer(
                SnapshotPipeServer.PackagedPipeName,
                collector,
                PackageNamedPipeServerFactory.Create);
            await server.RunAsync(CancellationToken.None).ConfigureAwait(false);
            return 0;
        }
        catch
        {
            return 1;
        }
    }
}
