using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ServicePipeConnectorTests
{
    [Theory]
    [InlineData("S-1-5-18", true)]
    [InlineData("S-1-5-32-544", true)]
    [InlineData("S-1-5-21-1004336348-1177238915-682003330-1001", false)]
    [InlineData("S-1-5-11", false)]
    [InlineData("S-1-1-0", false)]
    public void OnlySystemOrAdministratorsOwnTheTrustedPipe(string sid, bool trusted)
    {
        Assert.Equal(trusted, ServicePipeConnector.IsTrustedOwner(sid));
    }

    [Fact]
    public void MissingOwnerIsNeverTrusted()
    {
        Assert.False(ServicePipeConnector.IsTrustedOwner(null));
    }

    [Fact]
    public void NonWindowsHostsReportNotRunning()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        Assert.Equal(
            ServicePipeState.NotRunning,
            ServicePipeConnector.Connect("pdc-missing", TimeSpan.FromMilliseconds(10), out var pipe));
        Assert.Null(pipe);
    }
}
