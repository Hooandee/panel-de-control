using PanelDeControl.Core.Capabilities;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Capabilities;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class CapabilityInventoryTests
{
    [Theory]
    [InlineData("ROG Xbox Ally X RC73XA", "ASUSTeK COMPUTER INC.", new[] { CapabilityIds.SensorDriver, CapabilityIds.AsusAtkAcpi, CapabilityIds.RivalArmouryCrate })]
    [InlineData("83E1", "LENOVO", new[] { CapabilityIds.SensorDriver, CapabilityIds.LenovoGameZone, CapabilityIds.LenovoOtherMethod, CapabilityIds.LenovoFanMethod, CapabilityIds.RivalLegionSpace })]
    [InlineData("83N0", "LENOVO", new[] { CapabilityIds.SensorDriver, CapabilityIds.LenovoGameZone, CapabilityIds.LenovoOtherMethod, CapabilityIds.LenovoFanMethod, CapabilityIds.RivalLegionSpace })]
    [InlineData("Claw 8 AI+ A2VM", "Micro-Star International Co., Ltd.", new[] { CapabilityIds.SensorDriver, CapabilityIds.MsiAcpi, CapabilityIds.RivalMsiCenter, CapabilityIds.RivalIntelThermal })]
    [InlineData("Claw A8", "Micro-Star International Co., Ltd.", new[] { CapabilityIds.SensorDriver, CapabilityIds.MsiAcpi, CapabilityIds.RivalMsiCenter })]
    [InlineData("Some Laptop 15", "Contoso", new[] { CapabilityIds.SensorDriver })]
    public void EachFamilyOnlyProbesItsOwnMechanisms(string model, string manufacturer, string[] expected)
    {
        var inventory = Collector(model, manufacturer, new FakeSources()).Collect();

        Assert.Equal(expected, inventory.Entries.Select(entry => entry.Id).ToArray());
    }

    [Fact]
    public void ProbeOutcomesAreReportedWithoutInference()
    {
        var sources = new FakeSources
        {
            DevicePaths = { @"\\.\ATKACPI" },
            RunningServices = { "ArmouryCrateSEService" },
            Access = new SensorAccess(true, false),
        };

        var inventory = Collector("ROG Xbox Ally X RC73XA", "ASUSTeK COMPUTER INC.", sources).Collect();

        Assert.Equal("rog_xbox_ally_x", inventory.DeviceKey);
        Assert.Equal(CapabilityStatus.Absent, Entry(inventory, CapabilityIds.SensorDriver).Status);
        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.AsusAtkAcpi).Status);
        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.RivalArmouryCrate).Status);
    }

    [Fact]
    public void DriverWithoutElevationNeedsPermission()
    {
        var sources = new FakeSources { Access = new SensorAccess(false, true) };

        var inventory = Collector("83E1", "LENOVO", sources).Collect();

        Assert.Equal(CapabilityStatus.PermissionRequired, Entry(inventory, CapabilityIds.SensorDriver).Status);
    }

    [Fact]
    public void LenovoWmiClassesAndRivalProcessesAreDetected()
    {
        var sources = new FakeSources
        {
            WmiClasses = { "LENOVO_GAMEZONE_DATA", "LENOVO_OTHER_METHOD" },
            RunningProcesses = { "LegionSpace" },
        };

        var inventory = Collector("83N0", "LENOVO", sources).Collect();

        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.LenovoGameZone).Status);
        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.LenovoOtherMethod).Status);
        Assert.Equal(CapabilityStatus.Absent, Entry(inventory, CapabilityIds.LenovoFanMethod).Status);
        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.RivalLegionSpace).Status);
    }

    [Fact]
    public void AFailingProbeNeverHidesTheOthers()
    {
        var sources = new FakeSources
        {
            ThrowOnWmi = new UnauthorizedAccessException("denied"),
            RunningServices = { "MSI Foundation Service" },
        };

        var inventory = Collector("Claw 8 AI+ A2VM", "Micro-Star International Co., Ltd.", sources).Collect();

        var msi = Entry(inventory, CapabilityIds.MsiAcpi);
        Assert.Equal(CapabilityStatus.PermissionRequired, msi.Status);
        Assert.Equal("probe_permission_required", msi.ErrorCode);
        Assert.Equal(CapabilityStatus.Present, Entry(inventory, CapabilityIds.RivalMsiCenter).Status);
    }

    [Fact]
    public void UnexpectedProbeFailureIsAFault()
    {
        var sources = new FakeSources { ThrowOnWmi = new InvalidOperationException("private detail") };

        var entry = Entry(Collector("83E1", "LENOVO", sources).Collect(), CapabilityIds.LenovoGameZone);

        Assert.Equal(CapabilityStatus.Fault, entry.Status);
        Assert.Equal("probe_failed", entry.ErrorCode);
    }

    [Fact]
    public void HungProbeTimesOut()
    {
        using var release = new ManualResetEventSlim();
        var sources = new FakeSources { BlockWmi = release };
        var collector = Collector("83E1", "LENOVO", sources, TimeSpan.FromMilliseconds(50));

        var inventory = collector.Collect();
        release.Set();

        var entry = Entry(inventory, CapabilityIds.LenovoGameZone);
        Assert.Equal(CapabilityStatus.Fault, entry.Status);
        Assert.Equal("probe_timeout", entry.ErrorCode);
        Assert.Equal(CapabilityStatus.Absent, Entry(inventory, CapabilityIds.RivalLegionSpace).Status);
    }

    [Fact]
    public void HungProbeIsNotRestartedOnTheNextRequest()
    {
        using var release = new ManualResetEventSlim();
        var sources = new FakeSources { BlockWmi = release };
        var collector = Collector("83E1", "LENOVO", sources, TimeSpan.FromMilliseconds(50));

        collector.Collect();
        var second = collector.Collect();
        var callsWhileHung = sources.WmiCalls;
        release.Set();

        Assert.Equal("probe_busy", Entry(second, CapabilityIds.LenovoGameZone).ErrorCode);
        Assert.Equal(3, callsWhileHung);
    }

    [Fact]
    public void ProbesShareOneTimeBudget()
    {
        using var release = new ManualResetEventSlim();
        var sources = new FakeSources { BlockWmi = release };
        var collector = Collector("83E1", "LENOVO", sources, TimeSpan.FromMilliseconds(200));

        var watch = System.Diagnostics.Stopwatch.StartNew();
        collector.Collect();
        watch.Stop();
        release.Set();

        Assert.True(watch.Elapsed < TimeSpan.FromMilliseconds(500), watch.Elapsed.ToString());
    }

    [Fact]
    public void InventoryRoundTripsThroughTheWireCodec()
    {
        var inventory = Collector("83E1", "LENOVO", new FakeSources()).Collect();

        var decoded = CapabilityWireCodec.Deserialize(CapabilityWireCodec.Serialize(inventory));

        Assert.Equal(inventory.DeviceKey, decoded.DeviceKey);
        Assert.Equal(
            inventory.Entries.Select(entry => (entry.Id, entry.Status)),
            decoded.Entries.Select(entry => (entry.Id, entry.Status)));
    }

    private static CapabilityEntry Entry(CapabilityInventory inventory, string id)
    {
        return Assert.Single(inventory.Entries, entry => entry.Id == id);
    }

    private static CapabilityInventoryCollector Collector(
        string model,
        string manufacturer,
        FakeSources sources,
        TimeSpan? timeout = null)
    {
        return new CapabilityInventoryCollector(
            new FixedClock(),
            new FixedIdentity(model, manufacturer),
            new CapabilityProbeCatalog(sources, sources, sources, sources),
            timeout);
    }

    private sealed class FixedClock : IClock
    {
        public DateTimeOffset UtcNow { get; } = new(2026, 9, 22, 23, 0, 0, TimeSpan.Zero);
    }

    private sealed class FixedIdentity : IDeviceIdentityReader
    {
        private readonly string model;
        private readonly string manufacturer;

        public FixedIdentity(string model, string manufacturer)
        {
            this.model = model;
            this.manufacturer = manufacturer;
        }

        public DeviceIdentity Read()
        {
            return DeviceIdentity.FromDmi(DeviceCatalogResource.TryLoad(), manufacturer, model, string.Empty);
        }
    }

    private sealed class FakeSources : IWmiClassCatalog, IDevicePathProbe, ISoftwareInventory, ISensorAccessProbe
    {
        public HashSet<string> WmiClasses { get; } = new(StringComparer.Ordinal);

        public HashSet<string> DevicePaths { get; } = new(StringComparer.Ordinal);

        public HashSet<string> RunningServices { get; } = new(StringComparer.Ordinal);

        public HashSet<string> RunningProcesses { get; } = new(StringComparer.Ordinal);

        public SensorAccess Access { get; set; } = new(true, true);

        public Exception? ThrowOnWmi { get; set; }

        public ManualResetEventSlim? BlockWmi { get; set; }

        private int wmiCalls;

        public int WmiCalls => Volatile.Read(ref wmiCalls);

        public bool HasClass(string wmiNamespace, string className)
        {
            Interlocked.Increment(ref wmiCalls);
            BlockWmi?.Wait();
            if (ThrowOnWmi is not null)
            {
                throw ThrowOnWmi;
            }

            return wmiNamespace == @"root\WMI" && WmiClasses.Contains(className);
        }

        public bool Exists(string devicePath)
        {
            return DevicePaths.Contains(devicePath);
        }

        public bool IsServiceRunning(string serviceName)
        {
            return RunningServices.Contains(serviceName);
        }

        public bool IsProcessRunning(string processName)
        {
            return RunningProcesses.Contains(processName);
        }

        public SensorAccess Probe()
        {
            return Access;
        }
    }
}
