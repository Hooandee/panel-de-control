using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public enum ServiceSnapshotOutcome
{
    Received,
    NotRunning,
    Unavailable,
}

public sealed record ServiceSnapshotResult(ServiceSnapshotOutcome Outcome, HardwareSnapshot? Snapshot)
{
    public static ServiceSnapshotResult NotRunning { get; } = new(ServiceSnapshotOutcome.NotRunning, null);

    public static ServiceSnapshotResult Unavailable { get; } = new(ServiceSnapshotOutcome.Unavailable, null);
}

public interface IServiceSnapshotSource
{
    ServiceSnapshotResult Read();
}

public sealed class ServiceSnapshotClient : IServiceSnapshotSource
{
    public const string PipeName = "PanelDeControl.Service";

    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromMilliseconds(500);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(3);

    public ServiceSnapshotResult Read()
    {
        if (!OperatingSystem.IsWindows() || !File.Exists($@"\\.\pipe\{PipeName}"))
        {
            return ServiceSnapshotResult.NotRunning;
        }

        try
        {
            using var pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
            pipe.Connect((int)ConnectTimeout.TotalMilliseconds);

            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 256, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 256, leaveOpen: true)
            {
                AutoFlush = true,
            };
            writer.WriteLine("snapshot");
            var line = reader.ReadLineAsync().WaitAsync(ResponseTimeout).GetAwaiter().GetResult();
            return string.IsNullOrWhiteSpace(line)
                ? ServiceSnapshotResult.Unavailable
                : new ServiceSnapshotResult(ServiceSnapshotOutcome.Received, TelemetryWireCodec.Deserialize(line));
        }
        catch
        {
            return ServiceSnapshotResult.Unavailable;
        }
    }
}
