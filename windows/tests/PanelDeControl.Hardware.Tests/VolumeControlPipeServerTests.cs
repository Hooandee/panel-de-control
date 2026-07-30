using System.IO.Pipes;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class VolumeControlPipeServerTests
{
    [Fact]
    public async Task GetRequestReturnsTheControllerReadback()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var server = new VolumeControlPipeServer(
            pipeName,
            new FixedVolumeController(0.64),
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            VolumeControlRequest.Get(),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.Equal(0.64, response.ObservedLevel);
    }

    [Fact]
    public async Task SetRequestReturnsTheControllerReadback()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var server = new VolumeControlPipeServer(
            pipeName,
            new FixedVolumeController(0.20),
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            VolumeControlRequest.Set(0.70),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(0.70, response.RequestedLevel);
        Assert.Equal(0.70, response.ObservedLevel);
    }

    [Fact]
    public async Task MalformedRequestFailsClosedWithoutCallingTheController()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var controller = new CountingVolumeController();
        var server = new VolumeControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestRawAsync(
            pipeName,
            "not-json",
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("invalid_control_request", response.ErrorCode);
        Assert.Equal(0, controller.GetCount);
        Assert.Equal(0, controller.SetCount);
    }

    [Fact]
    public async Task OversizedRequestIsRejectedBeforeControllerAccess()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var controller = new CountingVolumeController();
        var server = new VolumeControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestRawAsync(
            pipeName,
            new string('x', 257),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("control_request_too_long", response.ErrorCode);
        Assert.Equal(0, controller.GetCount);
        Assert.Equal(0, controller.SetCount);
    }

    [Fact]
    public async Task ControllerFailureReturnsSanitizedFault()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var server = new VolumeControlPipeServer(
            pipeName,
            new ThrowingVolumeController(),
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            VolumeControlRequest.Get(),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("volume_control_failed", response.ErrorCode);
        Assert.DoesNotContain(
            "private endpoint identifier",
            VolumeControlWireCodec.SerializeResponse(response));
    }

    [Fact]
    public async Task RunLoopStopsWhenCancelled()
    {
        var server = new VolumeControlPipeServer(
            $"pvc-{Guid.NewGuid():N}",
            new CountingVolumeController(),
            CreateTestPipe);
        using var cancellation = new CancellationTokenSource(
            TimeSpan.FromMilliseconds(30));

        await server.RunUntilCancelledAsync(cancellation.Token);
    }

    [Fact]
    public async Task SlowControllerReturnsBoundedFaultWithoutStartingAnotherCall()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        using var controller = new BlockingVolumeController();
        var server = new VolumeControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe,
            TimeSpan.FromMilliseconds(30));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var firstServerTask = server.RunOnceAsync(timeout.Token);
        var firstResponse = await RequestAsync(
            pipeName,
            VolumeControlRequest.Get(),
            timeout.Token);
        await firstServerTask;

        Assert.Equal(ControlStatus.Fault, firstResponse.Status);
        Assert.Equal("volume_control_timeout", firstResponse.ErrorCode);
        Assert.Equal(1, controller.GetCount);

        var secondServerTask = server.RunOnceAsync(timeout.Token);
        var secondResponse = await RequestAsync(
            pipeName,
            VolumeControlRequest.Get(),
            timeout.Token);
        await secondServerTask;

        Assert.Equal(ControlStatus.Fault, secondResponse.Status);
        Assert.Equal("volume_control_busy", secondResponse.ErrorCode);
        Assert.Equal(1, controller.GetCount);
        controller.Release();
    }

    [Fact]
    public async Task TimedOutSetIsUnverifiableAndNeverReportedAsApplied()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        using var controller = new BlockingVolumeController();
        var server = new VolumeControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe,
            TimeSpan.FromMilliseconds(30));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            VolumeControlRequest.Set(0.75),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(0.75, response.RequestedLevel);
        Assert.Null(response.ObservedLevel);
        Assert.Equal("volume_control_timeout", response.ErrorCode);
        Assert.Equal(1, controller.SetCount);
        controller.Release();
    }

    [Fact]
    public async Task ClientDisconnectDoesNotCrashTheBrokerLoop()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        var server = new VolumeControlPipeServer(
            pipeName,
            new CountingVolumeController(),
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using (var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous))
        {
            await client.ConnectAsync(timeout.Token);
        }

        await serverTask;
    }

    [Fact]
    public async Task ClientDisconnectAfterSendingDoesNotCrashTheBrokerLoop()
    {
        var pipeName = $"pvc-{Guid.NewGuid():N}";
        using var controller = new BlockingVolumeController();
        var server = new VolumeControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using (var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous))
        {
            await client.ConnectAsync(timeout.Token);
            await using var writer = new StreamWriter(client, leaveOpen: true)
            {
                AutoFlush = true,
            };
            await writer.WriteLineAsync(
                VolumeControlWireCodec.SerializeRequest(
                    VolumeControlRequest.Set(0.80)));
            Assert.True(controller.WaitUntilEntered(TimeSpan.FromSeconds(1)));
        }

        controller.Release();
        await serverTask;
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

    private static async Task<VolumeControlResponse> RequestAsync(
        string pipeName,
        VolumeControlRequest request,
        CancellationToken cancellationToken)
    {
        return await RequestRawAsync(
            pipeName,
            VolumeControlWireCodec.SerializeRequest(request),
            cancellationToken);
    }

    private static async Task<VolumeControlResponse> RequestRawAsync(
        string pipeName,
        string payload,
        CancellationToken cancellationToken)
    {
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(cancellationToken);
        await using var writer = new StreamWriter(client, leaveOpen: true)
        {
            AutoFlush = true,
        };
        using var reader = new StreamReader(client, leaveOpen: true);

        await writer.WriteLineAsync(payload);
        var responsePayload = await reader.ReadLineAsync(cancellationToken);
        Assert.NotNull(responsePayload);
        return VolumeControlWireCodec.DeserializeResponse(responsePayload);
    }

    private sealed class FixedVolumeController : ISystemVolumeController
    {
        private double level;

        public FixedVolumeController(double level)
        {
            this.level = level;
        }

        public VolumeControlResponse Get()
        {
            return VolumeControlResponse.Available(level);
        }

        public VolumeControlResponse Set(double requestedLevel)
        {
            level = requestedLevel;
            return VolumeControlResponse.Applied(requestedLevel, level);
        }
    }

    private sealed class CountingVolumeController : ISystemVolumeController
    {
        public int GetCount { get; private set; }

        public int SetCount { get; private set; }

        public VolumeControlResponse Get()
        {
            GetCount++;
            return VolumeControlResponse.Available(0.50);
        }

        public VolumeControlResponse Set(double requestedLevel)
        {
            SetCount++;
            return VolumeControlResponse.Applied(requestedLevel, requestedLevel);
        }
    }

    private sealed class ThrowingVolumeController : ISystemVolumeController
    {
        public VolumeControlResponse Get()
        {
            throw new InvalidOperationException("private endpoint identifier");
        }

        public VolumeControlResponse Set(double requestedLevel)
        {
            throw new InvalidOperationException("private endpoint identifier");
        }
    }

    private sealed class BlockingVolumeController :
        ISystemVolumeController,
        IDisposable
    {
        private readonly ManualResetEventSlim release = new();
        private readonly ManualResetEventSlim entered = new();

        public int GetCount { get; private set; }

        public int SetCount { get; private set; }

        public VolumeControlResponse Get()
        {
            GetCount++;
            entered.Set();
            release.Wait();
            return VolumeControlResponse.Available(0.50);
        }

        public VolumeControlResponse Set(double requestedLevel)
        {
            SetCount++;
            entered.Set();
            release.Wait();
            return VolumeControlResponse.Applied(requestedLevel, requestedLevel);
        }

        public void Release()
        {
            release.Set();
        }

        public bool WaitUntilEntered(TimeSpan timeout)
        {
            return entered.Wait(timeout);
        }

        public void Dispose()
        {
            release.Set();
            entered.Dispose();
            release.Dispose();
        }
    }
}
