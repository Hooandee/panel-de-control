using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class BrightnessControlPipeServer
{
    private const int MaximumRequestLength = 192;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Display";

    private readonly string pipeName;
    private readonly IDisplayBrightnessController brightnessController;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan operationTimeout;
    private readonly TimeSpan requestTimeout;
    private Task<BrightnessControlResponse>? activeOperation;

    public BrightnessControlPipeServer(
        string pipeName,
        IDisplayBrightnessController brightnessController,
        Func<string, NamedPipeServerStream> pipeFactory,
        TimeSpan? operationTimeout = null,
        TimeSpan? requestTimeout = null)
    {
        var effectiveOperationTimeout =
            operationTimeout ?? TimeSpan.FromSeconds(2);
        var effectiveRequestTimeout =
            requestTimeout ?? TimeSpan.FromSeconds(2);
        if (effectiveOperationTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(operationTimeout));
        }

        if (effectiveRequestTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(requestTimeout));
        }

        this.pipeName = pipeName;
        this.brightnessController = brightnessController;
        this.pipeFactory = pipeFactory;
        this.operationTimeout = effectiveOperationTimeout;
        this.requestTimeout = effectiveRequestTimeout;
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
            PipeRequest payload;
            using (var requestLifetime =
                CancellationTokenSource.CreateLinkedTokenSource(
                    cancellationToken))
            {
                requestLifetime.CancelAfter(requestTimeout);
                try
                {
                    payload = await ReadRequestAsync(
                        reader,
                        requestLifetime.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                    when (!cancellationToken.IsCancellationRequested)
                {
                    return;
                }
            }

            if (payload.Disconnected)
            {
                return;
            }

            var response = payload.TooLong
                ? BrightnessControlResponse.Rejected(
                    "brightness_request_too_long")
                : await HandleRequestAsync(
                    payload.Value ?? string.Empty,
                    cancellationToken).ConfigureAwait(false);

            await TryWriteResponseAsync(writer, response).ConfigureAwait(false);
        }
        finally
        {
            await TryDisposeWriterAsync(writer).ConfigureAwait(false);
        }
    }

    private async Task<BrightnessControlResponse> HandleRequestAsync(
        string payload,
        CancellationToken cancellationToken)
    {
        BrightnessControlRequest request;
        try
        {
            request = BrightnessControlWireCodec.DeserializeRequest(payload);
        }
        catch
        {
            return BrightnessControlResponse.Rejected(
                "invalid_brightness_request");
        }

        if (activeOperation is { IsCompleted: false })
        {
            return PendingOperation(request, "brightness_control_busy");
        }

        activeOperation = Task.Run(() => Dispatch(request));
        var currentOperation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(currentOperation, timeout).ConfigureAwait(false) !=
            currentOperation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return PendingOperation(request, "brightness_control_timeout");
        }

        activeOperation = null;
        return await currentOperation.ConfigureAwait(false);
    }

    private BrightnessControlResponse Dispatch(BrightnessControlRequest request)
    {
        try
        {
            return request.Operation switch
            {
                BrightnessControlOperation.Get => brightnessController.Get(),
                BrightnessControlOperation.Set => brightnessController.Set(
                    request.RequestedPercentage!.Value),
                _ => BrightnessControlResponse.Rejected(
                    "unsupported_brightness_operation"),
            };
        }
        catch
        {
            return BrightnessControlResponse.Fault(
                "brightness_control_failed");
        }
    }

    private static BrightnessControlResponse PendingOperation(
        BrightnessControlRequest request,
        string errorCode)
    {
        return request.Operation == BrightnessControlOperation.Set
            ? BrightnessControlResponse.Unverifiable(
                request.RequestedPercentage!.Value,
                null,
                errorCode)
            : BrightnessControlResponse.Fault(errorCode);
    }

    private static async Task TryWriteResponseAsync(
        StreamWriter writer,
        BrightnessControlResponse response)
    {
        try
        {
            await writer
                .WriteLineAsync(
                    BrightnessControlWireCodec.SerializeResponse(response))
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
