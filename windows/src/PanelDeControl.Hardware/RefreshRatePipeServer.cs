using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class RefreshRatePipeServer
{
    private const int MaximumRequestLength = 256;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Refresh";

    private readonly string pipeName;
    private readonly IRefreshRateController controller;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan operationTimeout;
    private Task<RefreshRateResponse>? activeOperation;

    public RefreshRatePipeServer(
        string pipeName,
        IRefreshRateController controller,
        Func<string, NamedPipeServerStream> pipeFactory,
        TimeSpan? operationTimeout = null)
    {
        var effectiveOperationTimeout =
            operationTimeout ?? TimeSpan.FromSeconds(2);
        if (effectiveOperationTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(operationTimeout));
        }

        this.pipeName = pipeName;
        this.controller = controller;
        this.pipeFactory = pipeFactory;
        this.operationTimeout = effectiveOperationTimeout;
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
        await using var server = await PipeInstances
            .CreateAsync(pipeFactory, pipeName, cancellationToken)
            .ConfigureAwait(false);
        using var clientRelease = PipeClientRelease.For(server);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);

        using var reader = new StreamReader(
            server,
            new UTF8Encoding(false),
            false,
            256,
            leaveOpen: true);
        var writer = new StreamWriter(
            server,
            new UTF8Encoding(false),
            256,
            leaveOpen: true)
        {
            AutoFlush = true,
        };

        try
        {
            var payload = await ReadRequestAsync(reader, cancellationToken)
                .ConfigureAwait(false);
            if (payload.Disconnected)
            {
                return;
            }

            RefreshRateResponse response;
            if (payload.TooLong)
            {
                response = RefreshRateResponse.Rejected(
                    "control_request_too_long");
            }
            else
            {
                response = await HandleRequestAsync(
                    payload.Value ?? string.Empty,
                    cancellationToken).ConfigureAwait(false);
            }

            await TryWriteResponseAsync(writer, response).ConfigureAwait(false);
        }
        finally
        {
            await TryDisposeWriterAsync(writer).ConfigureAwait(false);
        }
    }

    private static async Task TryWriteResponseAsync(
        StreamWriter writer,
        RefreshRateResponse response)
    {
        try
        {
            await writer
                .WriteLineAsync(RefreshRateWireCodec.SerializeResponse(response))
                .ConfigureAwait(false);
        }
        catch (IOException)
        {
        }
        catch (ObjectDisposedException)
        {
        }
    }

    private static async Task TryDisposeWriterAsync(StreamWriter writer)
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

    private async Task<RefreshRateResponse> HandleRequestAsync(
        string payload,
        CancellationToken cancellationToken)
    {
        RefreshRateRequest request;
        try
        {
            request = RefreshRateWireCodec.DeserializeRequest(payload);
        }
        catch
        {
            return RefreshRateResponse.Rejected("invalid_refresh_request");
        }

        if (activeOperation is { IsCompleted: false })
        {
            return PendingOperation(request, "refresh_rate_busy");
        }

        activeOperation = Task.Run(() => Dispatch(request));
        var currentOperation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(currentOperation, timeout).ConfigureAwait(false) !=
            currentOperation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return PendingOperation(request, "refresh_rate_timeout");
        }

        activeOperation = null;
        return await currentOperation.ConfigureAwait(false);
    }

    private RefreshRateResponse Dispatch(RefreshRateRequest request)
    {
        try
        {
            return request.Operation switch
            {
                RefreshRateOperation.Get => controller.Get(),
                RefreshRateOperation.Set => controller.Set(request.RequestedHertz!.Value),
                _ => RefreshRateResponse.Rejected("unsupported_control_operation"),
            };
        }
        catch
        {
            return RefreshRateResponse.Fault("refresh_rate_control_failed");
        }
    }

    private static RefreshRateResponse PendingOperation(
        RefreshRateRequest request,
        string errorCode)
    {
        return request.Operation == RefreshRateOperation.Set
            ? RefreshRateResponse.Unverifiable(request.RequestedHertz!.Value, null, null, errorCode)
            : RefreshRateResponse.Fault(errorCode);
    }

    private static async Task<PipeRequest> ReadRequestAsync(
        StreamReader reader,
        CancellationToken cancellationToken)
    {
        var request = new StringBuilder(MaximumRequestLength);
        var character = new char[1];
        while (true)
        {
            var count = await reader
                .ReadAsync(character.AsMemory(0, 1), cancellationToken)
                .ConfigureAwait(false);
            if (count == 0)
            {
                return new PipeRequest(null, false, true);
            }

            if (character[0] == '\n')
            {
                return new PipeRequest(request.ToString(), false, false);
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (request.Length == MaximumRequestLength)
            {
                return new PipeRequest(null, true, false);
            }

            request.Append(character[0]);
        }
    }

    private readonly record struct PipeRequest(
        string? Value,
        bool TooLong,
        bool Disconnected);
}
