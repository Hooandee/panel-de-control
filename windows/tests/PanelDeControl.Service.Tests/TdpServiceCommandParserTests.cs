using PanelDeControl.Core.Controls;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class TdpServiceCommandParserTests
{
    [Theory]
    [InlineData("get", TdpControlOperation.Get, null)]
    [InlineData("experimental on", TdpControlOperation.EnableExperimental, null)]
    [InlineData("experimental off", TdpControlOperation.DisableExperimental, null)]
    [InlineData("set 0", TdpControlOperation.Set, 0)]
    [InlineData("set 35", TdpControlOperation.Set, 35)]
    [InlineData("set 999", TdpControlOperation.Set, 999)]
    public void CanonicalCommandsAreAccepted(
        string text,
        TdpControlOperation operation,
        int? requestedWatts)
    {
        var parsed = TdpServiceCommandParser.TryParse(text, out var command);

        Assert.True(parsed);
        Assert.Equal(operation, command.Operation);
        Assert.Equal(requestedWatts, command.RequestedWatts);
    }

    [Theory]
    [InlineData("")]
    [InlineData("GET")]
    [InlineData("set")]
    [InlineData("set +25")]
    [InlineData("set -1")]
    [InlineData("set 025")]
    [InlineData("set 25.0")]
    [InlineData("set 25 ")]
    [InlineData(" set 25")]
    [InlineData("set 25 extra")]
    [InlineData("set 1000")]
    public void NonCanonicalValuesAreRejected(string text)
    {
        Assert.False(TdpServiceCommandParser.TryParse(text, out _));
    }
}
