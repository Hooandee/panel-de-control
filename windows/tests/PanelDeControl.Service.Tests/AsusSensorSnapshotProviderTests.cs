using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class AsusSensorSnapshotProviderTests
{
    private static readonly DateTimeOffset Now = new(2026, 9, 24, 10, 0, 0, TimeSpan.Zero);

    [Theory]
    [InlineData(AsusSensorRegister.CpuFan, 0x00010026u, 3800)]
    [InlineData(AsusSensorRegister.GpuFan, 0x00010025u, 3700)]
    [InlineData(AsusSensorRegister.CpuTemperature, 0x00010033u, 51)]
    [InlineData(AsusSensorRegister.CpuTemperature, 0x0001002Fu, 47)]
    [InlineData(AsusSensorRegister.GpuTemperature, 0x00010027u, 39)]
    [InlineData(AsusSensorRegister.CpuFan, 0x00010000u, 0)]
    [InlineData(AsusSensorRegister.CpuFan, 0x00010064u, 10000)]
    [InlineData(AsusSensorRegister.CpuTemperature, 0x0001007Du, 125)]
    public void DecodesPhysicalFramesAndBoundaryValues(AsusSensorRegister register, uint raw, double expected)
    {
        Assert.Equal(expected, AsusAtkSensorTransport.Decode(register, raw));
    }

    [Theory]
    [InlineData(AsusSensorRegister.CpuFan, 0u)]
    [InlineData(AsusSensorRegister.CpuFan, 38u)]
    [InlineData(AsusSensorRegister.CpuFan, 0xFFFFFFFFu)]
    [InlineData(AsusSensorRegister.CpuFan, 0x00030026u)]
    [InlineData(AsusSensorRegister.CpuFan, 0x00010065u)]
    [InlineData(AsusSensorRegister.CpuTemperature, 0x00010000u)]
    [InlineData(AsusSensorRegister.GpuTemperature, 0x0001007Eu)]
    public void InvalidFramesNeverBecomeReadings(AsusSensorRegister register, uint raw)
    {
        Assert.Null(AsusAtkSensorTransport.Decode(register, raw));
    }

    [Theory]
    [InlineData(AsusSensorRegister.CpuFan, 0x00110013u)]
    [InlineData(AsusSensorRegister.GpuFan, 0x00110014u)]
    [InlineData(AsusSensorRegister.CpuTemperature, 0x00120094u)]
    [InlineData(AsusSensorRegister.GpuTemperature, 0x00120097u)]
    public void FramesOnlyRequestDsts(AsusSensorRegister register, uint id)
    {
        var frame = AsusAtkSensorTransport.BuildReadFrame(register);
        Assert.Equal(16, frame.Length);
        Assert.Equal(0x53545344u, BitConverter.ToUInt32(frame, 0));
        Assert.Equal(8u, BitConverter.ToUInt32(frame, 4));
        Assert.Equal(id, BitConverter.ToUInt32(frame, 8));
        Assert.Equal(0u, BitConverter.ToUInt32(frame, 12));
    }

    [Fact]
    public void PhysicalFramesFillMissingLhmTemperaturesAndBothFans()
    {
        var provider = Create(new FixedSnapshot(
            Missing("cpu.temperature", "sensor_driver_missing"), Missing("gpu.temperature", "sensor_not_found")),
            new Transport());
        var snapshot = provider.Capture();
        Assert.Equal(51, Reading(snapshot, "cpu.temperature").Value);
        Assert.Equal(39, Reading(snapshot, "gpu.temperature").Value);
        Assert.Equal(3800, Reading(snapshot, "fan.cpu.rpm").Value);
        Assert.Equal(3700, Reading(snapshot, "fan.gpu.rpm").Value);
        Assert.All(snapshot.Readings, r => Assert.Equal("asus/atk-dsts", r.Source));
    }

    [Fact]
    public void PlausibleLhmTemperaturesAndOtherReadingsArePreserved()
    {
        var local = new FixedSnapshot(
            TelemetryReading.Available("cpu.temperature", "CPU", 61, "°C", "lhm"),
            TelemetryReading.Available("gpu.temperature", "GPU", 59, "°C", "lhm"),
            TelemetryReading.Available("battery.level", "Batería", 84, "%", "win32"));
        var snapshot = Create(local, new Transport()).Capture();
        Assert.Equal(61, Reading(snapshot, "cpu.temperature").Value);
        Assert.Equal("lhm", Reading(snapshot, "gpu.temperature").Source);
        Assert.Equal(84, Reading(snapshot, "battery.level").Value);
    }

    [Fact]
    public void InvalidLhmValueDoesNotSuppressValidAsusTemperature()
    {
        var snapshot = Create(new FixedSnapshot(TelemetryReading.Available(
            "cpu.temperature", "CPU", 0, "°C", "lhm")), new Transport()).Capture();
        Assert.Equal(51, Reading(snapshot, "cpu.temperature").Value);
    }

    [Theory]
    [InlineData("ROG Ally RC71L_RC71L", "RC71L")]
    [InlineData("ROG Ally X RC72LA_RC72LA", "RC72LA")]
    [InlineData("ROG Xbox Ally X RC73XA_RC73XA", "RC72LA")]
    [InlineData("Unknown", "")]
    public void OtherMachinesNeverInvokeAsus(string product, string board)
    {
        var calls = 0;
        var provider = Create(new FixedSnapshot(), new Transport(_ => { calls++; return 0x10026; }),
            new Identity(product, board));
        Assert.Empty(provider.Capture().Readings);
        Assert.Equal(0, calls);
    }

    [Fact]
    public void OneFailedRegisterDoesNotDiscardTheOtherSensors()
    {
        var provider = Create(new FixedSnapshot(), new Transport(r =>
            r == AsusSensorRegister.CpuFan ? throw new IOException() : Transport.Raw(r)));
        var snapshot = provider.Capture();
        Assert.Null(Reading(snapshot, "fan.cpu.rpm").Value);
        Assert.Equal("asus_probe_failed", Reading(snapshot, "fan.cpu.rpm").ErrorCode);
        Assert.Equal(3700, Reading(snapshot, "fan.gpu.rpm").Value);
        Assert.Equal(51, Reading(snapshot, "cpu.temperature").Value);
    }

    [Fact]
    public void HungProbeIsDedicatedBoundedAndNeverRelaunchedUntilItFinishes()
    {
        using var release = new ManualResetEventSlim();
        using var entered = new ManualResetEventSlim();
        using var finished = new ManualResetEventSlim();
        var calls = 0;
        var poolThread = true;
        var provider = Create(new FixedSnapshot(), new Transport(r =>
        {
            if (r != AsusSensorRegister.CpuFan) return Transport.Raw(r);
            Interlocked.Increment(ref calls);
            poolThread = Thread.CurrentThread.IsThreadPoolThread;
            entered.Set();
            release.Wait();
            finished.Set();
            return 0x10026;
        }));
        try
        {
            var first = provider.Capture();
            Assert.True(entered.Wait(TimeSpan.FromSeconds(1)));
            Assert.Equal("asus_probe_timeout", Reading(first, "fan.cpu.rpm").ErrorCode);
            Assert.Equal(3700, Reading(first, "fan.gpu.rpm").Value);
            var second = provider.Capture();
            Assert.Equal("asus_probe_busy", Reading(second, "fan.cpu.rpm").ErrorCode);
            Assert.Null(Reading(second, "fan.cpu.rpm").Value);
            Assert.Equal(1, calls);
            Assert.False(poolThread);
        }
        finally
        {
            release.Set();
            Assert.True(finished.Wait(TimeSpan.FromSeconds(1)));
        }
    }

    [Fact]
    public void HungLhmDoesNotBlockAsusAndIsNotRelaunched()
    {
        using var release = new ManualResetEventSlim();
        using var finished = new ManualResetEventSlim();
        var calls = 0;
        var local = new CallbackSnapshot(() =>
        {
            Interlocked.Increment(ref calls);
            release.Wait();
            finished.Set();
            return new HardwareSnapshot(Now, "ROG Xbox Ally X", Array.Empty<TelemetryReading>());
        });
        var provider = Create(local, new Transport());
        try
        {
            Assert.Equal(51, Reading(provider.Capture(), "cpu.temperature").Value);
            Assert.Equal(3800, Reading(provider.Capture(), "fan.cpu.rpm").Value);
            Assert.Equal(1, calls);
        }
        finally
        {
            release.Set();
            Assert.True(finished.Wait(TimeSpan.FromSeconds(1)));
        }
    }

    [Fact]
    public void SlowBaselineOnOtherMachineRetainsItsOriginalBehavior()
    {
        var local = new CallbackSnapshot(() =>
        {
            Thread.Sleep(75);
            return new HardwareSnapshot(Now, "Other", new[] {
                TelemetryReading.Available("cpu.load", "CPU", 42, "%", "lhm") });
        });
        var provider = new AsusSensorSnapshotProvider(local, new Identity("ROG Ally RC71L_RC71L", "RC71L"),
            new Transport(), new Clock(), TimeSpan.FromMilliseconds(20));
        Assert.Equal(42, Reading(provider.Capture(), "cpu.load").Value);
    }

    [Fact]
    public void LateIdentityIsRetainedWithoutRepeatingWmi()
    {
        var calls = 0;
        var identity = new CallbackIdentity(() =>
        {
            Interlocked.Increment(ref calls);
            Thread.Sleep(150);
            return new Identity().Read();
        });
        var provider = new AsusSensorSnapshotProvider(new FixedSnapshot(), identity,
            new Transport(), new Clock(), TimeSpan.FromMilliseconds(40));
        provider.Capture();
        Thread.Sleep(200);
        Assert.Equal(3800, Reading(provider.Capture(), "fan.cpu.rpm").Value);
        Assert.Equal(1, calls);
    }

    private sealed class CallbackIdentity(Func<DeviceIdentity> read) : IDeviceIdentityReader
    {
        public DeviceIdentity Read() => read();
    }

    private static AsusSensorSnapshotProvider Create(IHardwareSnapshotProvider local, IAsusSensorTransport transport,
        IDeviceIdentityReader? identity = null) => new(local, identity ?? new Identity(), transport, new Clock(), TimeSpan.FromMilliseconds(150));
    private static TelemetryReading Reading(HardwareSnapshot s, string id) => Assert.Single(s.Readings, r => r.Id == id);
    private static TelemetryReading Missing(string id, string error) => TelemetryReading.Unavailable(id, id, "°C", ReadingStatus.Unavailable, error);
    private sealed class Clock : IClock { public DateTimeOffset UtcNow => Now; }
    private sealed class Identity(string product = "ROG Xbox Ally X RC73XA_RC73XA", string board = "RC73XA") : IDeviceIdentityReader
    {
        public DeviceIdentity Read() => DeviceIdentity.FromDmi(DeviceCatalogResource.TryLoad(), "ASUSTeK COMPUTER INC.", product, board);
    }
    private sealed class FixedSnapshot(params TelemetryReading[] readings) : IHardwareSnapshotProvider
    {
        public HardwareSnapshot Capture() => new(Now, "ROG Xbox Ally X", readings);
    }
    private sealed class CallbackSnapshot(Func<HardwareSnapshot> capture) : IHardwareSnapshotProvider
    {
        public HardwareSnapshot Capture() => capture();
    }
    private sealed class Transport(Func<AsusSensorRegister, uint?>? read = null) : IAsusSensorTransport
    {
        public uint? Read(AsusSensorRegister register) => read is null ? Raw(register) : read(register);
        public static uint Raw(AsusSensorRegister register) => register switch
        {
            AsusSensorRegister.CpuFan => 0x10026,
            AsusSensorRegister.GpuFan => 0x10025,
            AsusSensorRegister.CpuTemperature => 0x10033,
            _ => 0x10027,
        };
    }
}
