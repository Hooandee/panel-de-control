using PanelDeControl.Hardware;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class SnapshotServiceWorkerTests
{
    [Fact]
    public async Task ServerFailuresAreRetriedUntilTheServiceStops()
    {
        var server = new ScriptedServer(failures: 2);
        var worker = new SnapshotServiceWorker(server, TimeSpan.FromMilliseconds(5));

        await worker.StartAsync(CancellationToken.None);
        Assert.True(SpinWait.SpinUntil(() => server.Runs >= 4, TimeSpan.FromSeconds(5)));
        await worker.StopAsync(CancellationToken.None);

        var runsAfterStop = server.Runs;
        await Task.Delay(50);
        Assert.Equal(runsAfterStop, server.Runs);
    }

    [Fact]
    public async Task IdleServerRunsAreRestarted()
    {
        var server = new ScriptedServer(failures: 0);
        var worker = new SnapshotServiceWorker(server, TimeSpan.FromMilliseconds(5));

        await worker.StartAsync(CancellationToken.None);
        Assert.True(SpinWait.SpinUntil(() => server.Runs >= 3, TimeSpan.FromSeconds(5)));
        await worker.StopAsync(CancellationToken.None);
    }

    private sealed class ScriptedServer : ISnapshotServer
    {
        private int failures;
        private int runs;

        public ScriptedServer(int failures)
        {
            this.failures = failures;
        }

        public int Runs => Volatile.Read(ref runs);

        public async Task RunAsync(TimeSpan idleTimeout, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref runs);
            await Task.Delay(1, cancellationToken);
            if (Interlocked.Decrement(ref failures) >= 0)
            {
                throw new IOException("pipe broke");
            }
        }
    }
}
