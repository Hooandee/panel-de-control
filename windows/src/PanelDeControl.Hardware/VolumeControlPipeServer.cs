using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class VolumeControlPipeServer
{
    private const int MaximumRequestLength = 256;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Control";

    private readonly string pipeName;
    private readonly ISystemVolumeController volumeController;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan operationTimeout;
    private Task<VolumeControlResponse>? activeOperation;

    public VolumeControlPipeServer(
        string pipeName,
        ISystemVolumeController volumeController,
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
        this.volumeController = volumeController;
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
            var payload = await ReadRequestAsync(reader, cancellationToken)
                .ConfigureAwait(false);
            if (payload.Disconnected)
            {
                return;
            }

            VolumeControlResponse response;
            if (payload.TooLong)
            {
                response = VolumeControlResponse.Rejected(
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
        VolumeControlResponse response)
    {
        try
        {
            await writer
                .WriteLineAsync(VolumeControlWireCodec.SerializeResponse(response))
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

    private async Task<VolumeControlResponse> HandleRequestAsync(
        string payload,
        CancellationToken cancellationToken)
    {
        VolumeControlRequest request;
        try
        {
            request = VolumeControlWireCodec.DeserializeRequest(payload);
        }
        catch
        {
            return VolumeControlResponse.Rejected("invalid_control_request");
        }

        if (activeOperation is { IsCompleted: false })
        {
            return PendingOperation(request, "volume_control_busy");
        }

        activeOperation = Task.Run(() => Dispatch(request));
        var currentOperation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(currentOperation, timeout).ConfigureAwait(false) !=
            currentOperation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return PendingOperation(request, "volume_control_timeout");
        }

        activeOperation = null;
        return await currentOperation.ConfigureAwait(false);
    }

    private VolumeControlResponse Dispatch(VolumeControlRequest request)
    {
        try
        {
            return request.Operation switch
            {
                VolumeControlOperation.Get => volumeController.Get(),
                VolumeControlOperation.Set => volumeController.Set(
                    request.RequestedLevel!.Value),
                VolumeControlOperation.SetMute => volumeController.SetMute(
                    request.RequestedMuted!.Value),
                _ => VolumeControlResponse.Rejected(
                    "unsupported_control_operation"),
            };
        }
        catch
        {
            return VolumeControlResponse.Fault("volume_control_failed");
        }
    }

    private static VolumeControlResponse PendingOperation(
        VolumeControlRequest request,
        string errorCode)
    {
        return request.Operation switch
        {
            VolumeControlOperation.Set => VolumeControlResponse.Unverifiable(
                request.RequestedLevel!.Value,
                null,
                errorCode),
            VolumeControlOperation.SetMute =>
                VolumeControlResponse.MuteUnverifiable(
                    request.RequestedMuted!.Value,
                    null,
                    errorCode),
            _ => VolumeControlResponse.Fault(errorCode),
        };
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
