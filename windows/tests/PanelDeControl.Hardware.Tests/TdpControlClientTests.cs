using System.IO.Pipes;
using PanelDeControl.Core.Controls;
using PanelDeControl.GameBar;
using Xunit;

namespace PanelDeControl.Hardware.Tests
{
    public sealed class TdpControlClientTests
    {
        [Fact]
        public async Task LostResponseAfterAWriteDoesNotRestartTheBrokerOrRetry()
        {
            HardwareBrokerLauncher.StartCount = 0;
            var server = new NamedPipeServerStream(@"LOCAL\PanelDeControl.Tdp",
                PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            Task<TdpControlResponse> request;
            await using (server)
            {
                var connection = server.WaitForConnectionAsync(timeout.Token);
                request = new TdpControlClient().SetAsync(25);
                await connection;
                using var reader = new StreamReader(server, leaveOpen: true);
                var payload = await reader.ReadLineAsync(timeout.Token);
                var command = TdpControlWireCodec.DeserializeRequest(payload!);
                Assert.Equal(TdpControlOperation.Set, command.Operation);
                Assert.Equal(25, command.RequestedWatts);
            }

            var response = await request.WaitAsync(timeout.Token);

            Assert.Equal(ControlStatus.Unverifiable, response.Status);
            Assert.Equal("tdp_response_unavailable", response.ErrorCode);
            Assert.Equal(25, response.RequestedWatts);
            Assert.Null(response.AppliedWatts);
            Assert.False(response.ExperimentalStateKnown);
            Assert.Equal(0, HardwareBrokerLauncher.StartCount);
        }
    }
}

namespace PanelDeControl.GameBar
{
    internal static class HardwareBrokerLauncher
    {
        public static int StartCount { get; set; }

        public static Task EnsureStartedAsync()
        {
            StartCount++;
            return Task.CompletedTask;
        }
    }
}
