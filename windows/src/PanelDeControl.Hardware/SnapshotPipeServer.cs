using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public sealed class SnapshotPipeServer
{
    private const int MaximumCommandLength = 64;

    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Telemetry";

    private readonly string pipeName;
    private readonly IHardwareSnapshotProvider snapshotProvider;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;
    private readonly TimeSpan captureTimeout;
    private Task<HardwareSnapshot>? activeCapture;

    public SnapshotPipeServer(
        string pipeName,
        IHardwareSnapshotProvider snapshotProvider,
        Func<string, NamedPipeServerStream> pipeFactory,
        TimeSpan? captureTimeout = null)
    {
        if (string.IsNullOrWhiteSpace(pipeName))
        {
            throw new ArgumentException("Pipe name must not be empty.", nameof(pipeName));
        }

        var effectiveCaptureTimeout = captureTimeout ?? TimeSpan.FromSeconds(10);
        if (effectiveCaptureTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(captureTimeout));
        }

        this.pipeName = pipeName;
        this.snapshotProvider = snapshotProvider;
        this.pipeFactory = pipeFactory;
        this.captureTimeout = effectiveCaptureTimeout;
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        await RunAsync(TimeSpan.FromSeconds(30), cancellationToken).ConfigureAwait(false);
    }

    public async Task RunAsync(
        TimeSpan idleTimeout,
        CancellationToken cancellationToken)
    {
        if (idleTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(idleTimeout));
        }

        while (!cancellationToken.IsCancellationRequested)
        {
            using var idleCancellation =
                CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            idleCancellation.CancelAfter(idleTimeout);
            try
            {
                await RunOnceAsync(idleCancellation.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return;
            }
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

        PipeCommand command;
        try
        {
            command = await ReadCommandAsync(reader, cancellationToken).ConfigureAwait(false);
        }
        catch (IOException)
        {
            return;
        }
        catch (ObjectDisposedException)
        {
            return;
        }

        var snapshot = command.TooLong
            ? Fault("command_too_long")
            : command.Value == "snapshot"
                ? await CaptureAsync(cancellationToken).ConfigureAwait(false)
                : Fault("unsupported_command");
        await TryWriteResponseAsync(writer, snapshot).ConfigureAwait(false);
    }

    private static async Task TryWriteResponseAsync(
        StreamWriter writer,
        HardwareSnapshot snapshot)
    {
        try
        {
            await writer
                .WriteLineAsync(TelemetryWireCodec.Serialize(snapshot))
                .ConfigureAwait(false);
        }
        catch (IOException)
        {
        }
        catch (ObjectDisposedException)
        {
        }
    }

    private static async Task<PipeCommand> ReadCommandAsync(
        StreamReader reader,
        CancellationToken cancellationToken)
    {
        var command = new StringBuilder(MaximumCommandLength);
        var character = new char[1];
        while (true)
        {
            var count = await reader
                .ReadAsync(character.AsMemory(0, 1), cancellationToken)
                .ConfigureAwait(false);
            if (count == 0 || character[0] == '\n')
            {
                return new PipeCommand(command.ToString(), false);
            }

            if (character[0] == '\r')
            {
                continue;
            }

            if (command.Length == MaximumCommandLength)
            {
                return new PipeCommand(null, true);
            }

            command.Append(character[0]);
        }
    }

    private async Task<HardwareSnapshot> CaptureAsync(CancellationToken cancellationToken)
    {
        if (activeCapture is { IsCompleted: false })
        {
            return Fault("snapshot_busy");
        }

        activeCapture = Task.Run(Capture);
        var currentCapture = activeCapture;
        var timeout = Task.Delay(captureTimeout, cancellationToken);
        if (await Task.WhenAny(currentCapture, timeout).ConfigureAwait(false) != currentCapture)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Fault("snapshot_timeout");
        }

        activeCapture = null;
        return await currentCapture.ConfigureAwait(false);
    }

    private HardwareSnapshot Capture()
    {
        try
        {
            return snapshotProvider.Capture();
        }
        catch
        {
            return Fault("snapshot_capture_failed");
        }
    }

    private static HardwareSnapshot Fault(string errorCode)
    {
        return new HardwareSnapshot(
            DateTimeOffset.UtcNow,
            "Unknown device",
            new[]
            {
                TelemetryReading.Unavailable(
                    "broker.request",
                    "Conexión",
                    "-",
                    ReadingStatus.Fault,
                    errorCode),
            });
    }

    private readonly record struct PipeCommand(string? Value, bool TooLong);
}
