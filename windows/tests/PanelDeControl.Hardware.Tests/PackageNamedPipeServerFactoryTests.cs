using System.Runtime.Versioning;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class PackageNamedPipeServerFactoryTests
{
    [Fact]
    [SupportedOSPlatform("windows")]
    public void ControlFactoryFailsClosedOutsideWindows()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        Assert.Throws<PlatformNotSupportedException>(
            () => PackageNamedPipeServerFactory.CreateControl("test-control"));
    }
}
