using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class TdpControlPipeServerTests
{
    [Fact]
    public async Task SetIsForwardedWithoutHardwareAccessInTheBroker()
    {
        var pipeName = "pt-" + Guid.NewGuid().ToString("N")[..12];
        var proxy = new CountingProxy();
        var server = new TdpControlPipeServer(
            pipeName,
            proxy,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(
            pipeName,
            TdpControlRequest.Set(30),
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(1, proxy.SendCount);
        Assert.Equal(TdpControlOperation.Set, proxy.LastRequest!.Operation);
        Assert.Equal(30, proxy.LastRequest.RequestedWatts);
    }

    [Fact]
    public async Task InvalidJsonNeverReachesTheServiceProxy()
    {
        var pipeName = "pt-" + Guid.NewGuid().ToString("N")[..12];
        var proxy = new CountingProxy();
        var server = new TdpControlPipeServer(
            pipeName,
            proxy,
            CreateTestPipe);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestRawAsync(
            pipeName,
            "not-json",
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("invalid_tdp_request", response.ErrorCode);
        Assert.Equal(0, proxy.SendCount);
    }

    [Theory]
    [InlineData(TdpControlOperation.Get, "get")]
    [InlineData(TdpControlOperation.EnableExperimental, "experimental on")]
    [InlineData(TdpControlOperation.DisableExperimental, "experimental off")]
    [InlineData(TdpControlOperation.Set, "set 25")]
    public void ServiceClientUsesOnlyCanonicalCommands(
        TdpControlOperation operation,
        string expected)
    {
        var request = operation switch
        {
            TdpControlOperation.Get => TdpControlRequest.Get(),
            TdpControlOperation.EnableExperimental =>
                TdpControlRequest.EnableExperimental(),
            TdpControlOperation.DisableExperimental =>
                TdpControlRequest.DisableExperimental(),
            _ => TdpControlRequest.Set(25),
        };

        Assert.Equal(expected, ServiceTdpClient.BuildCommand(request));
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

    private static Task<TdpControlResponse> RequestAsync(
        string pipeName,
        TdpControlRequest request,
        CancellationToken cancellationToken)
    {
        return RequestRawAsync(
            pipeName,
            TdpControlWireCodec.SerializeRequest(request),
            cancellationToken);
    }

    private static async Task<TdpControlResponse> RequestRawAsync(
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
        using var reader = new StreamReader(
            client,
            new UTF8Encoding(false),
            false,
            256,
            leaveOpen: true);
        await using var writer = new StreamWriter(
            client,
            new UTF8Encoding(false),
            256,
            leaveOpen: true)
        {
            AutoFlush = true,
        };
        await writer.WriteLineAsync(payload);
        var response = await reader.ReadLineAsync(cancellationToken);
        return TdpControlWireCodec.DeserializeResponse(response!);
    }

    private sealed class CountingProxy : ITdpControlProxy
    {
        public int SendCount { get; private set; }

        public TdpControlRequest? LastRequest { get; private set; }

        public TdpControlResponse Send(TdpControlRequest request)
        {
            SendCount++;
            LastRequest = request;
            return request.Operation == TdpControlOperation.Set
                ? TdpControlResponse.Indeterminate(
                    false,
                    request.RequestedWatts!.Value,
                    "readback_unavailable")
                : TdpControlResponse.Available(
                    false,
                    7,
                    25,
                    new[] { 13, 17, 25 },
                    false);
        }
    }
}
