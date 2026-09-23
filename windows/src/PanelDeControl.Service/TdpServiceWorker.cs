using Microsoft.Extensions.Hosting;

namespace PanelDeControl.Service;

public sealed class TdpServiceWorker : BackgroundService
{
    private readonly ITdpServiceServer server;
    private readonly TimeSpan retryDelay;

    public TdpServiceWorker(
        ITdpServiceServer server,
        TimeSpan? retryDelay = null)
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
                await server.RunUntilCancelledAsync(stoppingToken)
                    .ConfigureAwait(false);
                return;
            }
            catch (OperationCanceledException)
                when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch
            {
                try
                {
                    await Task.Delay(retryDelay, stoppingToken)
                        .ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    return;
                }
            }
        }
    }
}
