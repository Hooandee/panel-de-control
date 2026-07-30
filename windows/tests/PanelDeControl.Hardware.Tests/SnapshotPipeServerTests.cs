using System.IO.Pipes;
using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class SnapshotPipeServerTests
{
    [Fact]
    public async Task SnapshotCommandReturnsOneBoundedSnapshot()
    {
        var pipeName = $"pdc-tests-{Guid.NewGuid():N}";
        var expected = new HardwareSnapshot(
            new DateTimeOffset(2026, 7, 29, 20, 30, 0, TimeSpan.Zero),
            "ROG Xbox Ally X RC73XA_RC73XA",
            new[]
            {
                TelemetryReading.Available("cpu.temperature", "CPU", 71, "°C", "test"),
            });
        var server = CreateServer(pipeName, new FixedSnapshotProvider(expected));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(timeout.Token);
        await using var writer = new StreamWriter(client, leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);

        await writer.WriteLineAsync("snapshot");
        var payload = await reader.ReadLineAsync(timeout.Token);
        await serverTask;

        Assert.NotNull(payload);
        var snapshot = TelemetryWireCodec.Deserialize(payload);
        Assert.Equal("ROG Xbox Ally X RC73XA_RC73XA", snapshot.DeviceModel);
        Assert.Equal(71, Assert.Single(snapshot.Readings).Value);
    }

    [Fact]
    public async Task UnknownCommandFailsClosedWithoutCallingHardware()
    {
        var pipeName = $"pdc-tests-{Guid.NewGuid():N}";
        var provider = new CountingSnapshotProvider();
        var server = CreateServer(pipeName, provider);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(timeout.Token);
        await using var writer = new StreamWriter(client, leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);

        await writer.WriteLineAsync("write-tdp 35");
        var payload = await reader.ReadLineAsync(timeout.Token);
        await serverTask;

        Assert.NotNull(payload);
        var snapshot = TelemetryWireCodec.Deserialize(payload);
        var reading = Assert.Single(snapshot.Readings);
        Assert.Equal(ReadingStatus.Fault, reading.Status);
        Assert.Equal("unsupported_command", reading.ErrorCode);
        Assert.Equal(0, provider.CaptureCount);
    }

    [Fact]
    public async Task ServerStopsAfterAnIdlePeriod()
    {
        var pipeName = $"pdc-tests-{Guid.NewGuid():N}";
        var server = CreateServer(pipeName, new CountingSnapshotProvider());

        await server.RunAsync(TimeSpan.FromMilliseconds(30), CancellationToken.None);
    }

    [Fact]
    public async Task OversizedCommandIsRejectedBeforeHardwareAccess()
    {
        var pipeName = $"pdc-tests-{Guid.NewGuid():N}";
        var provider = new CountingSnapshotProvider();
        var server = CreateServer(pipeName, provider);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(timeout.Token);
        await using var writer = new StreamWriter(client, leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);

        await writer.WriteLineAsync(new string('x', 65));
        var payload = await reader.ReadLineAsync(timeout.Token);
        await serverTask;

        Assert.NotNull(payload);
        var reading = Assert.Single(TelemetryWireCodec.Deserialize(payload).Readings);
        Assert.Equal("command_too_long", reading.ErrorCode);
        Assert.Equal(0, provider.CaptureCount);
    }

    [Fact]
    public async Task SlowCaptureReturnsBoundedFaultWithoutStartingAnotherCapture()
    {
        var pipeName = $"pdc-tests-{Guid.NewGuid():N}";
        using var provider = new BlockingSnapshotProvider();
        var server = new SnapshotPipeServer(
            pipeName,
            provider,
            CreateTestPipe,
            TimeSpan.FromMilliseconds(30));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var firstServerTask = server.RunOnceAsync(timeout.Token);
        var firstReading = await RequestAsync(pipeName, timeout.Token);
        await firstServerTask;

        Assert.Equal("snapshot_timeout", firstReading.ErrorCode);
        Assert.Equal(1, provider.CaptureCount);

        var secondServerTask = server.RunOnceAsync(timeout.Token);
        var secondReading = await RequestAsync(pipeName, timeout.Token);
        await secondServerTask;

        Assert.Equal("snapshot_busy", secondReading.ErrorCode);
        Assert.Equal(1, provider.CaptureCount);
        provider.Release();
    }

    private static SnapshotPipeServer CreateServer(
        string pipeName,
        IHardwareSnapshotProvider provider)
    {
        return new SnapshotPipeServer(pipeName, provider, CreateTestPipe);
    }

    private static NamedPipeServerStream CreateTestPipe(string pipeName)
    {
        return new NamedPipeServerStream(
            pipeName,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous);
    }

    private static async Task<TelemetryReading> RequestAsync(
        string pipeName,
        CancellationToken cancellationToken)
    {
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(cancellationToken);
        await using var writer = new StreamWriter(client, leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);

        await writer.WriteLineAsync("snapshot");
        var payload = await reader.ReadLineAsync(cancellationToken);
        Assert.NotNull(payload);
        return Assert.Single(TelemetryWireCodec.Deserialize(payload).Readings);
    }

    private sealed class FixedSnapshotProvider : IHardwareSnapshotProvider
    {
        private readonly HardwareSnapshot snapshot;

        public FixedSnapshotProvider(HardwareSnapshot snapshot)
        {
            this.snapshot = snapshot;
        }

        public HardwareSnapshot Capture()
        {
            return snapshot;
        }
    }

    private sealed class CountingSnapshotProvider : IHardwareSnapshotProvider
    {
        public int CaptureCount { get; private set; }

        public HardwareSnapshot Capture()
        {
            CaptureCount++;
            return new HardwareSnapshot(
                DateTimeOffset.UtcNow,
                "Unexpected",
                Array.Empty<TelemetryReading>());
        }
    }

    private sealed class BlockingSnapshotProvider : IHardwareSnapshotProvider, IDisposable
    {
        private readonly ManualResetEventSlim release = new();

        public int CaptureCount { get; private set; }

        public HardwareSnapshot Capture()
        {
            CaptureCount++;
            release.Wait();
            return new HardwareSnapshot(
                DateTimeOffset.UtcNow,
                "Unexpected",
                Array.Empty<TelemetryReading>());
        }

        public void Release()
        {
            release.Set();
        }

        public void Dispose()
        {
            release.Set();
            release.Dispose();
        }
    }
}
