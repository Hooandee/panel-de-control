using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class CpuControlPipeServer
{
    private const int MaximumRequestLength = 256;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Cpu";

    private readonly string pipeName;
    private readonly ICpuController controller;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan operationTimeout;
    private Task<CpuControlResponse>? activeOperation;

    public CpuControlPipeServer(
        string pipeName,
        ICpuController controller,
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

            CpuControlResponse response;
            if (payload.TooLong)
            {
                response = CpuControlResponse.Rejected(
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
        CpuControlResponse response)
    {
        try
        {
            await writer
                .WriteLineAsync(CpuControlWireCodec.SerializeResponse(response))
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

    private async Task<CpuControlResponse> HandleRequestAsync(
        string payload,
        CancellationToken cancellationToken)
    {
        CpuControlRequest request;
        try
        {
            request = CpuControlWireCodec.DeserializeRequest(payload);
        }
        catch
        {
            return CpuControlResponse.Rejected("invalid_cpu_request");
        }

        if (activeOperation is { IsCompleted: false })
        {
            return PendingOperation(request, "cpu_control_busy");
        }

        activeOperation = Task.Run(() => Dispatch(request));
        var currentOperation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(currentOperation, timeout).ConfigureAwait(false) !=
            currentOperation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return PendingOperation(request, "cpu_control_timeout");
        }

        activeOperation = null;
        return await currentOperation.ConfigureAwait(false);
    }

    private CpuControlResponse Dispatch(CpuControlRequest request)
    {
        try
        {
            return request.Operation switch
            {
                CpuControlOperation.Get => controller.Get(),
                CpuControlOperation.SetBoost => controller.SetBoost(request.BoostEnabled!.Value),
                CpuControlOperation.SetMaximumState => controller.SetMaximumState(request.MaximumStatePercent!.Value),
                _ => CpuControlResponse.Rejected("unsupported_control_operation"),
            };
        }
        catch
        {
            return CpuControlResponse.Fault("cpu_control_failed");
        }
    }

    private static CpuControlResponse PendingOperation(
        CpuControlRequest request,
        string errorCode)
    {
        return request.Operation == CpuControlOperation.Get
            ? CpuControlResponse.Fault(errorCode)
            : CpuControlResponse.Unverifiable(null, null, errorCode);
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
