using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;

namespace PanelDeControl.Hardware;

/// <summary>
/// <c>LOCAL\PanelDeControl.Upscalers</c>: one request line in, one response line out.
/// </summary>
public sealed class UpscalersPipeServer
{
    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Upscalers";

    private readonly string pipeName;
    private readonly IUpscalersController controller;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;

    public UpscalersPipeServer(string pipeName, IUpscalersController controller, Func<string, NamedPipeServerStream> pipeFactory)
    {
        this.pipeName = pipeName;
        this.controller = controller;
        this.pipeFactory = pipeFactory;
    }

    public async Task RunUntilCancelledAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await RunOnceAsync(cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        await using var server = await PipeInstances.CreateAsync(pipeFactory, pipeName, cancellationToken).ConfigureAwait(false);
        using var clientRelease = PipeClientRelease.For(server);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
        using var reader = new StreamReader(server, new UTF8Encoding(false), false, 1024, leaveOpen: true);
        var writer = new StreamWriter(server, new UTF8Encoding(false), 4096, leaveOpen: true) { AutoFlush = true };
        try
        {
            using var requestTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            requestTimeout.CancelAfter(TimeSpan.FromSeconds(1));
            string? payload;
            try
            {
                payload = await ReadLineAsync(reader, requestTimeout.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return;
            }

            if (payload is null)
            {
                return;
            }

            UpscalersResponse response;
            try
            {
                var request = UpscalersWireCodec.DeserializeRequest(payload);
                response = await controller.HandleAsync(request, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is InvalidDataException or ArgumentException or System.Runtime.Serialization.SerializationException)
            {
                response = new UpscalersResponse { Status = UpscalersResponseStatus.Rejected, ErrorCode = "invalid_upscalers_request" };
            }

            try
            {
                string line;
                try
                {
                    line = UpscalersWireCodec.SerializeResponse(response);
                }
                catch (InvalidDataException)
                {
                    line = UpscalersWireCodec.SerializeResponse(UpscalersResponse.Fault("upscalers_response_invalid"));
                }

                await writer.WriteLineAsync(line).ConfigureAwait(false);
            }
            catch (IOException)
            {
            }
        }
        finally
        {
            try
            {
                await writer.DisposeAsync().ConfigureAwait(false);
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }
        }
    }

    private static async Task<string?> ReadLineAsync(StreamReader reader, CancellationToken cancellationToken)
    {
        var line = new StringBuilder();
        var character = new char[1];
        while (true)
        {
            if (await reader.ReadAsync(character.AsMemory(0, 1), cancellationToken).ConfigureAwait(false) == 0)
            {
                return null;
            }

            if (character[0] == '\n')
            {
                return line.ToString();
            }

            if (character[0] != '\r')
            {
                if (line.Length == UpscalersWireCodec.MaximumRequestLength)
                {
                    return null;
                }

                line.Append(character[0]);
            }
        }
    }
}
