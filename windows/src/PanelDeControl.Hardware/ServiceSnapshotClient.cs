using System.Text;
using PanelDeControl.Core.Capabilities;
using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware.Capabilities;

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
    private static readonly TimeSpan SnapshotResponseTimeout = TimeSpan.FromSeconds(3);
    private static readonly TimeSpan InventoryResponseTimeout = TimeSpan.FromSeconds(8);

    public ServiceSnapshotResult Read()
    {
        var (outcome, line) = Send("snapshot", SnapshotResponseTimeout);
        if (outcome != ServiceSnapshotOutcome.Received)
        {
            return new ServiceSnapshotResult(outcome, null);
        }

        try
        {
            return new ServiceSnapshotResult(outcome, TelemetryWireCodec.Deserialize(line!));
        }
        catch
        {
            return ServiceSnapshotResult.Unavailable;
        }
    }

    public CapabilityInventory ReadInventory(IClock clock)
    {
        var (outcome, line) = Send("inventory", InventoryResponseTimeout);
        if (outcome == ServiceSnapshotOutcome.Received)
        {
            try
            {
                return CapabilityWireCodec.Deserialize(line!);
            }
            catch
            {
                outcome = ServiceSnapshotOutcome.Unavailable;
            }
        }

        var entry = outcome == ServiceSnapshotOutcome.NotRunning
            ? new CapabilityEntry(CapabilityIds.Service, CapabilityStatus.Absent, "service_not_running")
            : new CapabilityEntry(CapabilityIds.Service, CapabilityStatus.Fault, "service_unavailable");
        return new CapabilityInventory(clock.UtcNow, "unknown", new[] { entry });
    }

    private static (ServiceSnapshotOutcome Outcome, string? Line) Send(string command, TimeSpan responseTimeout)
    {
        try
        {
            var state = ServicePipeConnector.Connect(PipeName, ConnectTimeout, out var connected);
            if (state == ServicePipeState.NotRunning)
            {
                return (ServiceSnapshotOutcome.NotRunning, null);
            }

            if (connected is null)
            {
                return (ServiceSnapshotOutcome.Unavailable, null);
            }

            using var pipe = connected;
            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 256, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 256, leaveOpen: true)
            {
                AutoFlush = true,
            };
            writer.WriteLine(command);
            var line = reader.ReadLineAsync().WaitAsync(responseTimeout).GetAwaiter().GetResult();
            return string.IsNullOrWhiteSpace(line)
                ? (ServiceSnapshotOutcome.Unavailable, null)
                : (ServiceSnapshotOutcome.Received, line);
        }
        catch
        {
            return (ServiceSnapshotOutcome.Unavailable, null);
        }
    }
}

public sealed class ServiceInventoryProvider : ICapabilityInventoryProvider
{
    private readonly ServiceSnapshotClient client;
    private readonly IClock clock;

    public ServiceInventoryProvider(ServiceSnapshotClient client, IClock clock)
    {
        this.client = client;
        this.clock = clock;
    }

    public CapabilityInventory Collect()
    {
        return client.ReadInventory(clock);
    }
}
