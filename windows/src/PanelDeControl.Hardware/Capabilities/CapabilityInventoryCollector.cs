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
        DeviceIdentity identity;
        try
        {
            identity = identityReader.Read();
        }
        catch
        {
            identity = DeviceIdentity.Unrecognized();
        }

        var entries = catalog.For(identity.Profile).Select(Run).ToArray();
        return new CapabilityInventory(clock.UtcNow, identity.ProfileId, entries);
    }

    private CapabilityEntry Run(ICapabilityProbe probe)
    {
        var task = Task.Factory.StartNew(
            probe.Probe,
            CancellationToken.None,
            TaskCreationOptions.LongRunning,
            TaskScheduler.Default);
        try
        {
            return task.Wait(probeTimeout)
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
