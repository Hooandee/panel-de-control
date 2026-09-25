using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class RefreshRateControllerTests
{
    [Fact]
    public void SetIsAppliedOnlyWhenTheDisplayReadsBackTheRate()
    {
        var display = new FakeDisplay(60, new[] { 60, 120 });
        var response = new RefreshRateController(display).Set(120);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(120, response.ObservedHertz);
    }

    [Fact]
    public void SetThatDoesNotStickIsUnverifiable()
    {
        var display = new FakeDisplay(60, new[] { 60, 120 }) { Sticks = false };
        var response = new RefreshRateController(display).Set(120);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(60, response.ObservedHertz);
        Assert.Equal("refresh_rate_mismatch", response.ErrorCode);
    }

    [Fact]
    public void UnsupportedRateNeverReachesTheDisplay()
    {
        var display = new FakeDisplay(60, new[] { 60, 120 });
        var response = new RefreshRateController(display).Set(90);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal(0, display.Writes);
    }

    [Fact]
    public void UnreadableDisplayIsUnavailable()
    {
        var response = new RefreshRateController(new FakeDisplay(null, Array.Empty<int>())).Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
    }

    [Fact]
    public async Task PipeServerReturnsTheCurrentRateAndSupportedModes()
    {
        var pipeName = $"prr-{Guid.NewGuid():N}";
        var server = new RefreshRatePipeServer(
            pipeName,
            new RefreshRateController(new FakeDisplay(120, new[] { 60, 120 })),
            name => new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await client.ConnectAsync(timeout.Token);
        await using var writer = new StreamWriter(client, new UTF8Encoding(false), leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);
        await writer.WriteLineAsync(RefreshRateWireCodec.SerializeRequest(RefreshRateRequest.Get()));
        var response = RefreshRateWireCodec.DeserializeResponse((await reader.ReadLineAsync(timeout.Token))!);
        await serverTask;

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.Equal(120, response.ObservedHertz);
        Assert.Equal(new[] { 60, 120 }, response.Supported);
    }

    private sealed class FakeDisplay : IDisplayModeProvider
    {
        private readonly int[] supported;
        private int? current;

        public FakeDisplay(int? current, int[] supported)
        {
            this.current = current;
            this.supported = supported;
        }

        public bool Sticks { get; init; } = true;

        public int Writes { get; private set; }

        public int? CurrentRefreshRate() => current;

        public IReadOnlyList<int> SupportedRefreshRates() => supported;

        public DisplayModeChange SetRefreshRate(int hertz)
        {
            Writes++;
            if (Sticks)
            {
                current = hertz;
            }

            return DisplayModeChange.Applied;
        }
    }
}
