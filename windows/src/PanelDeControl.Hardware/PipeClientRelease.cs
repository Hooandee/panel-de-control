using System.IO.Pipes;

namespace PanelDeControl.Hardware;

public readonly struct PipeClientRelease : IDisposable
{
    private readonly NamedPipeServerStream server;

    private PipeClientRelease(NamedPipeServerStream server)
    {
        this.server = server;
    }

    // Closing a connected server handle keeps the single pipe instance busy until
    // the client closes its end, so the next CreateNamedPipe fails with PIPE_BUSY.
    public static PipeClientRelease For(NamedPipeServerStream server) => new(server);

    public void Dispose()
    {
        if (server is null || !server.IsConnected)
        {
            return;
        }

        try
        {
            server.Disconnect();
        }
        catch (IOException)
        {
        }
        catch (ObjectDisposedException)
        {
        }
        catch (InvalidOperationException)
        {
        }
    }
}
