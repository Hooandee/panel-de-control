using PanelDeControl.Core.Capabilities;

namespace PanelDeControl.Hardware.Capabilities;

public interface ICapabilityInventoryProvider
{
    CapabilityInventory Collect();
}

public sealed class CapabilityInventoryCollector : ICapabilityInventoryProvider
{
    private readonly IClock clock;
    private readonly IDeviceIdentityReader identityReader;
    private readonly CapabilityProbeCatalog catalog;
    private readonly TimeSpan probeTimeout;
    private readonly Dictionary<string, Task<CapabilityStatus>> inFlight = new(StringComparer.Ordinal);
    private DeviceIdentity? cachedIdentity;

    public CapabilityInventoryCollector(
        IClock clock,
        IDeviceIdentityReader identityReader,
        CapabilityProbeCatalog catalog,
        TimeSpan? probeTimeout = null)
    {
        this.clock = clock;
        this.identityReader = identityReader;
        this.catalog = catalog;
        this.probeTimeout = probeTimeout ?? TimeSpan.FromSeconds(2);
    }

    public CapabilityInventory Collect()
    {
        var identity = ReadIdentity();
        var probes = catalog.For(identity.Profile);
        var started = probes.Select(probe => (Probe: probe, Task: Start(probe))).ToArray();
        var deadline = DateTime.UtcNow + probeTimeout;
        var entries = started.Select(item => Finish(item.Probe, item.Task, deadline)).ToArray();
        return new CapabilityInventory(clock.UtcNow, identity.ProfileId, entries);
    }

    private DeviceIdentity ReadIdentity()
    {
        if (cachedIdentity is not null)
        {
            return cachedIdentity;
        }

        try
        {
            var identity = identityReader.Read();
            if (identity.IsRecognized)
            {
                cachedIdentity = identity;
            }

            return identity;
        }
        catch
        {
            return DeviceIdentity.Unrecognized();
        }
    }

    private Task<CapabilityStatus>? Start(ICapabilityProbe probe)
    {
        lock (inFlight)
        {
            if (inFlight.TryGetValue(probe.Id, out var previous) && !previous.IsCompleted)
            {
                return null;
            }

            var task = Task.Factory.StartNew(
                probe.Probe,
                CancellationToken.None,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default);
            inFlight[probe.Id] = task;
            return task;
        }
    }

    private static CapabilityEntry Finish(ICapabilityProbe probe, Task<CapabilityStatus>? task, DateTime deadline)
    {
        if (task is null)
        {
            return new CapabilityEntry(probe.Id, CapabilityStatus.Fault, "probe_busy");
        }

        try
        {
            var remaining = deadline - DateTime.UtcNow;
            return task.Wait(remaining > TimeSpan.Zero ? remaining : TimeSpan.Zero)
                ? new CapabilityEntry(probe.Id, task.Result)
                : new CapabilityEntry(probe.Id, CapabilityStatus.Fault, "probe_timeout");
        }
        catch (AggregateException exception) when (exception.InnerException is UnauthorizedAccessException)
        {
            return new CapabilityEntry(probe.Id, CapabilityStatus.PermissionRequired, "probe_permission_required");
        }
        catch
        {
            return new CapabilityEntry(probe.Id, CapabilityStatus.Fault, "probe_failed");
        }
    }
}
