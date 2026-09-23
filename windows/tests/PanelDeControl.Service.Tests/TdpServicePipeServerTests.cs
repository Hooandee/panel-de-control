using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class TdpServicePipeServerTests
{
    [Fact]
    public async Task ClientIsVerifiedBeforeAWriteVerbIsParsedOrDispatched()
    {
        var pipeName = $"pdc-tdp-{Guid.NewGuid():N}";
        var endpoint = new CountingEndpoint();
        var server = new TdpServicePipeServer(
            pipeName,
            endpoint,
            CreateTestPipe,
            new FixedClientValidator(false));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await SendWithoutReadingAsync(pipeName, "set 25", timeout.Token);
        await serverTask;

        Assert.Equal(0, endpoint.SetCount);
        Assert.Equal(1, endpoint.ValidationOrder);
    }

    [Theory]
    [InlineData("set +25")]
    [InlineData("set 25.0")]
    [InlineData("set 25 extra")]
    public async Task InvalidValueIsRejectedBeforeEndpointAccess(string command)
    {
        var pipeName = $"pdc-tdp-{Guid.NewGuid():N}";
        var endpoint = new CountingEndpoint();
        var server = new TdpServicePipeServer(
            pipeName,
            endpoint,
            CreateTestPipe,
            new FixedClientValidator(true));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(pipeName, command, timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("invalid_tdp_command", response.ErrorCode);
        Assert.False(response.ExperimentalStateKnown);
        Assert.Equal(0, endpoint.SetCount);
    }

    [Fact]
    public async Task IncompleteCommandTimesOutBeforeEndpointAccess()
    {
        var pipeName = $"pdc-tdp-{Guid.NewGuid():N}";
        var endpoint = new CountingEndpoint();
        var server = new TdpServicePipeServer(
            pipeName,
            endpoint,
            CreateTestPipe,
            new FixedClientValidator(true),
            commandReadTimeout: TimeSpan.FromMilliseconds(50));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestIncompleteAsync(
            pipeName,
            "experimental ",
            timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("tdp_command_timeout", response.ErrorCode);
        Assert.False(response.ExperimentalStateKnown);
        Assert.Equal(0, endpoint.SetCount);
    }

    [Fact]
    public async Task CanonicalSetDispatchesTheStrictInteger()
    {
        var pipeName = $"pdc-tdp-{Guid.NewGuid():N}";
        var endpoint = new CountingEndpoint();
        var server = new TdpServicePipeServer(
            pipeName,
            endpoint,
            CreateTestPipe,
            new FixedClientValidator(true));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        var response = await RequestAsync(pipeName, "set 25", timeout.Token);
        await serverTask;

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(1, endpoint.SetCount);
        Assert.Equal(25, endpoint.LastRequestedWatts);
    }

    [Fact]
    public void PackagedBrokerIdentityRequiresThePinnedExecutableInsideItsPackage()
    {
        const string family = "PanelDeControl.Windows_abcde12345abc";
        const string root = @"C:\Program Files\WindowsApps\PanelDeControl.Windows";
        Assert.True(PackagedPipeClient.IsExpected(
            root + @"\HardwareBroker\PanelDeControl.Hardware.exe",
            family, family, root, PackagedTdpClientValidator.BrokerRelativePath));
        Assert.False(PackagedPipeClient.IsExpected(
            root + @"\PanelDeControl.GameBar.exe",
            family, family, root, PackagedTdpClientValidator.BrokerRelativePath));
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

    private static async Task<TdpControlResponse> RequestAsync(
        string pipeName,
        string command,
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
        await writer.WriteLineAsync(command);
        var line = await reader.ReadLineAsync(cancellationToken);
        return TdpControlWireCodec.DeserializeResponse(line!);
    }

    private static async Task SendWithoutReadingAsync(
        string pipeName,
        string command,
        CancellationToken cancellationToken)
    {
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await client.ConnectAsync(cancellationToken);
        try
        {
            await client.WriteAsync(
                Encoding.UTF8.GetBytes(command + "\n"),
                cancellationToken);
        }
        catch (IOException)
        {
        }
    }

    private static async Task<TdpControlResponse> RequestIncompleteAsync(
        string pipeName,
        string command,
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
        await client.WriteAsync(
            Encoding.UTF8.GetBytes(command),
            cancellationToken);
        var line = await reader.ReadLineAsync(cancellationToken);
        return TdpControlWireCodec.DeserializeResponse(line!);
    }

    private sealed class FixedClientValidator : IPipeClientValidator
    {
        private readonly bool trusted;

        public FixedClientValidator(bool trusted)
        {
            this.trusted = trusted;
        }

        public bool IsTrusted(NamedPipeServerStream pipe) => trusted;
    }

    private sealed class CountingEndpoint : ITdpControlEndpoint
    {
        public int ValidationOrder => SetCount == 0 ? 1 : 2;

        public int SetCount { get; private set; }

        public int? LastRequestedWatts { get; private set; }

        public TdpControlResponse Get() => State();

        public TdpControlResponse EnableExperimental() => State();

        public TdpControlResponse DisableExperimental() => State();

        public TdpControlResponse Set(int requestedWatts)
        {
            SetCount++;
            LastRequestedWatts = requestedWatts;
            return TdpControlResponse.Unverifiable(
                true,
                requestedWatts,
                requestedWatts,
                7,
                35,
                new[] { 13, 17, 25, 30 },
                true,
                "readback_unavailable");
        }

        private static TdpControlResponse State()
        {
            return TdpControlResponse.Available(
                false,
                7,
                25,
                new[] { 13, 17, 25 },
                false);
        }
    }
}
