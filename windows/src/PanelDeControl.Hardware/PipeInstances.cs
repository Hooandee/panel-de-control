using System.IO.Pipes;

namespace PanelDeControl.Hardware;

public static class PipeInstances
{
    private static readonly TimeSpan BusyRetryDelay = TimeSpan.FromMilliseconds(50);

    // Each pipe has a single instance and a departing client can keep it busy for a
    // moment after the server closes; retrying keeps the accept loop alive.
    public static async Task<NamedPipeServerStream> CreateAsync(
        Func<string, NamedPipeServerStream> pipeFactory,
        string pipeName,
        CancellationToken cancellationToken)
    {
        while (true)
        {
            try
            {
                return pipeFactory(pipeName);
            }
            catch (IOException)
            {
                await Task.Delay(BusyRetryDelay, cancellationToken).ConfigureAwait(false);
            }
        }
    }
}
