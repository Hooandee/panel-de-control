using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public interface ITdpServiceServer
{
    Task RunUntilCancelledAsync(CancellationToken cancellationToken);
}

public sealed class TdpServicePipeServer : ITdpServiceServer
{
    private const int MaximumCommandLength = 64;

    private readonly string pipeName;
    private readonly ITdpControlEndpoint endpoint;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly ITdpClientValidator clientValidator;
    private readonly TimeSpan operationTimeout;
    private readonly TimeSpan commandReadTimeout;
    private Task<TdpControlResponse>? activeOperation;

    public TdpServicePipeServer(
        string pipeName,
        ITdpControlEndpoint endpoint,
        Func<string, NamedPipeServerStream> pipeFactory,
        ITdpClientValidator clientValidator,
        TimeSpan? operationTimeout = null,
        TimeSpan? commandReadTimeout = null)
    {
        this.pipeName = pipeName;
        this.endpoint = endpoint;
        this.pipeFactory = pipeFactory;
        this.clientValidator = clientValidator;
        this.operationTimeout = operationTimeout ?? TimeSpan.FromSeconds(3);
        this.commandReadTimeout = commandReadTimeout ?? TimeSpan.FromSeconds(1);
        if (this.operationTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(operationTimeout));
        }
        if (this.commandReadTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(commandReadTimeout));
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
        await using var server = await PipeInstances
            .CreateAsync(pipeFactory, pipeName, cancellationToken)
            .ConfigureAwait(false);
        using var clientRelease = PipeClientRelease.For(server);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);
        if (!clientValidator.IsTrusted(server))
        {
            return;
        }

        using var reader = new StreamReader(
            server,
            new UTF8Encoding(false),
            false,
            128,
            leaveOpen: true);
        await using var writer = new StreamWriter(
            server,
            new UTF8Encoding(false),
            128,
            leaveOpen: true)
        {
            AutoFlush = true,
        };

        var raw = default(PipeCommand);
        var readTimedOut = false;
        using (var readTimeout = CancellationTokenSource.CreateLinkedTokenSource(
                   cancellationToken))
        {
            readTimeout.CancelAfter(commandReadTimeout);
            try
            {
                raw = await ReadCommandAsync(reader, readTimeout.Token)
                    .ConfigureAwait(false);
            }
            catch (OperationCanceledException)
                when (!cancellationToken.IsCancellationRequested)
            {
                readTimedOut = true;
            }
        }

        TdpControlResponse response;
        if (readTimedOut)
        {
            response = TdpControlResponse.Rejected(
                false,
                "tdp_command_timeout",
                experimentalStateKnown: false);
        }
        else if (raw.TooLong ||
            !TdpServiceCommandParser.TryParse(raw.Value, out var command))
        {
            response = TdpControlResponse.Rejected(
                experimentalEnabled: false,
                raw.TooLong ? "tdp_command_too_long" : "invalid_tdp_command",
                experimentalStateKnown: false);
        }
        else
        {
            response = await DispatchAsync(command, cancellationToken)
                .ConfigureAwait(false);
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

    private async Task<TdpControlResponse> DispatchAsync(
        TdpServiceCommand command,
        CancellationToken cancellationToken)
    {
        if (activeOperation is { IsCompleted: false })
        {
            return Pending(command, "tdp_operation_busy");
        }

        activeOperation = Task.Run(() => Dispatch(command));
        var operation = activeOperation;
        var timeout = Task.Delay(operationTimeout, cancellationToken);
        if (await Task.WhenAny(operation, timeout).ConfigureAwait(false) !=
            operation)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Pending(command, "tdp_operation_timeout");
        }

        activeOperation = null;
        return await operation.ConfigureAwait(false);
    }

    private TdpControlResponse Dispatch(TdpServiceCommand command)
    {
        try
        {
            return command.Operation switch
            {
                TdpControlOperation.Get => endpoint.Get(),
                TdpControlOperation.EnableExperimental =>
                    endpoint.EnableExperimental(),
                TdpControlOperation.DisableExperimental =>
                    endpoint.DisableExperimental(),
                TdpControlOperation.Set =>
                    endpoint.Set(command.RequestedWatts!.Value),
                _ => TdpControlResponse.Rejected(
                    false,
                    "unsupported_tdp_operation",
                    experimentalStateKnown: false),
            };
        }
        catch
        {
            return command.Operation == TdpControlOperation.Set
                ? TdpControlResponse.Indeterminate(
                    false,
                    command.RequestedWatts!.Value,
                    "tdp_operation_failed",
                    experimentalStateKnown: false)
                : TdpControlResponse.Fault(
                    false,
                    "tdp_operation_failed",
                    experimentalStateKnown: false);
        }
    }

    private static TdpControlResponse Pending(
        TdpServiceCommand command,
        string errorCode)
    {
        return command.Operation == TdpControlOperation.Set
            ? TdpControlResponse.Indeterminate(
                false,
                command.RequestedWatts!.Value,
                errorCode,
                experimentalStateKnown: false)
            : TdpControlResponse.Fault(
                false,
                errorCode,
                experimentalStateKnown: false);
    }

    private static async Task<PipeCommand> ReadCommandAsync(
        StreamReader reader,
        CancellationToken cancellationToken)
    {
        var value = new StringBuilder(MaximumCommandLength);
        var character = new char[1];
        while (true)
        {
            var count = await reader
                .ReadAsync(character.AsMemory(0, 1), cancellationToken)
                .ConfigureAwait(false);
            if (count == 0 || character[0] == '\n')
            {
                return new PipeCommand(value.ToString(), false);
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (value.Length == MaximumCommandLength)
            {
                return new PipeCommand(null, true);
            }

            value.Append(character[0]);
        }
    }

    private readonly record struct PipeCommand(string? Value, bool TooLong);
}
