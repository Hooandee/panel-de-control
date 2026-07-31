using System.IO.Pipes;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class BrightnessControlPipeServerTests
{
    [Fact]
    public async Task GetRequestReturnsTheObservedBrightness()
    {
        var pipeName = $"pbc-{Guid.NewGuid():N}";
        var server = new BrightnessControlPipeServer(
            pipeName,
            new CountingBrightnessController(64),
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            BrightnessControlRequest.Get(),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.Equal(64, response.ObservedPercentage);
    }

    [Fact]
    public async Task SetRequestCallsTheControllerExactlyOnce()
    {
        var pipeName = $"pbc-{Guid.NewGuid():N}";
        var controller = new CountingBrightnessController(20);
        var server = new BrightnessControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            BrightnessControlRequest.Set(70),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(70, response.ObservedPercentage);
        Assert.Equal(1, controller.SetCount);
    }

    [Fact]
    public async Task MalformedRequestFailsClosedWithoutCallingTheController()
    {
        var pipeName = $"pbc-{Guid.NewGuid():N}";
        var controller = new CountingBrightnessController(20);
        var server = new BrightnessControlPipeServer(
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
        Assert.Equal("invalid_brightness_request", response.ErrorCode);
        Assert.Equal(0, controller.GetCount);
        Assert.Equal(0, controller.SetCount);
    }

    [Fact]
    public async Task TimedOutSetIsUnverifiableAndIsNotRetried()
    {
        var pipeName = $"pbc-{Guid.NewGuid():N}";
        using var controller = new BlockingBrightnessController();
        var server = new BrightnessControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe,
            TimeSpan.FromMilliseconds(30));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            BrightnessControlRequest.Set(75),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(75, response.RequestedPercentage);
        Assert.Null(response.ObservedPercentage);
        Assert.Equal("brightness_control_timeout", response.ErrorCode);
        Assert.Equal(1, controller.SetCount);
        controller.Release();
    }

    [Fact]
    public async Task BusySetIsUnverifiableWithoutStartingAnotherWrite()
    {
        var pipeName = $"pbc-{Guid.NewGuid():N}";
        using var controller = new BlockingBrightnessController();
        var server = new BrightnessControlPipeServer(
            pipeName,
            controller,
            CreateTestPipe,
            TimeSpan.FromMilliseconds(30));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var firstServerTask = server.RunOnceAsync(timeout.Token);
        await RequestAsync(
            pipeName,
            BrightnessControlRequest.Set(75),
            timeout.Token);
        await firstServerTask;

        var secondServerTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            BrightnessControlRequest.Set(50),
            timeout.Token);
        await secondServerTask;

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Equal("brightness_control_busy", response.ErrorCode);
        Assert.Equal(1, controller.SetCount);
        controller.Release();
    }

    [Fact]
    public async Task RunLoopStopsWhenCancelled()
    {
        var server = new BrightnessControlPipeServer(
            $"pbc-{Guid.NewGuid():N}",
            new CountingBrightnessController(50),
            CreateTestPipe);
        using var cancellation = new CancellationTokenSource(
            TimeSpan.FromMilliseconds(30));

        await server.RunUntilCancelledAsync(cancellation.Token);
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

    private static async Task<BrightnessControlResponse> RequestAsync(
        string pipeName,
        BrightnessControlRequest request,
        CancellationToken cancellationToken)
    {
        return await RequestRawAsync(
            pipeName,
            BrightnessControlWireCodec.SerializeRequest(request),
            cancellationToken);
    }

    private static async Task<BrightnessControlResponse> RequestRawAsync(
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
        return BrightnessControlWireCodec.DeserializeResponse(responsePayload);
    }

    private sealed class CountingBrightnessController
        : IDisplayBrightnessController
    {
        private int percentage;

        public CountingBrightnessController(int percentage)
        {
            this.percentage = percentage;
        }

        public int GetCount { get; private set; }

        public int SetCount { get; private set; }

        public BrightnessControlResponse Get()
        {
            GetCount++;
            return BrightnessControlResponse.Available(percentage);
        }

        public BrightnessControlResponse Set(int requestedPercentage)
        {
            SetCount++;
            percentage = requestedPercentage;
            return BrightnessControlResponse.Applied(
                requestedPercentage,
                percentage);
        }
    }

    private sealed class BlockingBrightnessController
        : IDisplayBrightnessController, IDisposable
    {
        private readonly ManualResetEventSlim release = new();

        public int SetCount { get; private set; }

        public BrightnessControlResponse Get()
        {
            release.Wait();
            return BrightnessControlResponse.Available(50);
        }

        public BrightnessControlResponse Set(int requestedPercentage)
        {
            SetCount++;
            release.Wait();
            return BrightnessControlResponse.Applied(
                requestedPercentage,
                requestedPercentage);
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
