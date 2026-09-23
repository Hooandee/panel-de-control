using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class TdpControlPipeServer
{
    private const int MaximumRequestLength = 256;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Tdp";

    private readonly string pipeName;
    private readonly ITdpControlProxy proxy;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan operationTimeout;
    private Task<TdpControlResponse>? activeOperation;

    public TdpControlPipeServer(
        string pipeName,
        ITdpControlProxy proxy,
        Func<string, NamedPipeServerStream> pipeFactory,
        TimeSpan? operationTimeout = null)
    {
        this.pipeName = pipeName;
        this.proxy = proxy;
        this.pipeFactory = pipeFactory;
        this.operationTimeout = operationTimeout ?? TimeSpan.FromSeconds(7);
        if (this.operationTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(operationTimeout));
        }
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
        catch (OperationCanceledException)
            when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        await using var server = pipeFactory(pipeName);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
        using var reader = new StreamReader(
            server,
            new UTF8Encoding(false),
            false,
            256,
            leaveOpen: true);
        await using var writer = new StreamWriter(
            server,
            new UTF8Encoding(false),
            256,
            leaveOpen: true)
        {
            AutoFlush = true,
        };

        var payload = await ReadRequestAsync(reader, cancellationToken)
            .ConfigureAwait(false);
        TdpControlResponse response;
        if (payload.TooLong)
        {
            response = TdpControlResponse.Rejected(
                false,
                "tdp_request_too_long",
                experimentalStateKnown: false);
        }
        else
        {
            response = await HandleAsync(
                payload.Value ?? string.Empty,
                cancellationToken).ConfigureAwait(false);
        }

        try
        {
            await writer.WriteLineAsync(
                TdpControlWireCodec.SerializeResponse(response))
                .ConfigureAwait(false);
        }
        catch (IOException)
        {
        }
        catch (ObjectDisposedException)
        {
        }
    }

    private async Task<TdpControlResponse> HandleAsync(
        string payload,
        CancellationToken cancellationToken)
    {
        TdpControlRequest request;
        try
        {
            request = TdpControlWireCodec.DeserializeRequest(payload);
        }
        catch
        {
            return TdpControlResponse.Rejected(
                false,
                "invalid_tdp_request",
                experimentalStateKnown: false);
        }

        if (activeOperation is { IsCompleted: false })
        {
            return Pending(request, "tdp_proxy_busy");
        }

        activeOperation = Task.Run(() => proxy.Send(request));
        var operation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(operation, timeout).ConfigureAwait(false) !=
            operation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Pending(request, "tdp_proxy_timeout");
        }

        activeOperation = null;
        return await operation.ConfigureAwait(false);
    }

    private static TdpControlResponse Pending(
        TdpControlRequest request,
        string errorCode)
    {
        return request.Operation == TdpControlOperation.Set
            ? TdpControlResponse.Indeterminate(
                false,
                request.RequestedWatts!.Value,
                errorCode,
                experimentalStateKnown: false)
            : TdpControlResponse.Fault(
                false,
                errorCode,
                experimentalStateKnown: false);
    }

    private static async Task<PipeRequest> ReadRequestAsync(
        StreamReader reader,
        CancellationToken cancellationToken)
    {
        var value = new StringBuilder(MaximumRequestLength);
        var character = new char[1];
        while (true)
        {
            var count = await reader
                .ReadAsync(character.AsMemory(0, 1), cancellationToken)
                .ConfigureAwait(false);
            if (count == 0 || character[0] == '\n')
            {
                return new PipeRequest(value.ToString(), false);
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (value.Length == MaximumRequestLength)
            {
                return new PipeRequest(null, true);
            }

            value.Append(character[0]);
        }
    }

    private readonly record struct PipeRequest(string? Value, bool TooLong);
}
