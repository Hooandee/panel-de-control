using Microsoft.Extensions.Hosting;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public sealed class SnapshotServiceWorker : BackgroundService
{
    private static readonly TimeSpan ConnectionWait = TimeSpan.FromMinutes(5);

    private readonly ISnapshotServer server;
    private readonly TimeSpan retryDelay;

    public SnapshotServiceWorker(ISnapshotServer server, TimeSpan? retryDelay = null)
    {
        this.server = server;
        this.retryDelay = retryDelay ?? TimeSpan.FromSeconds(5);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await server.RunAsync(ConnectionWait, stoppingToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch
            {
                try
                {
                    await Task.Delay(retryDelay, stoppingToken).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
            }
        }
    }
}
