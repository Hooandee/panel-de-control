using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class PackagedPipeClientTests
{
    private const string Family = "PanelDeControl.Windows_abcde12345abc";
    private const string Root = @"C:\Program Files\WindowsApps\PanelDeControl.Windows";

    [Theory]
    [InlineData(PackagedWidgetClientValidator.WidgetRelativePath)]
    [InlineData(@"HardwareBroker\PanelDeControl.Hardware.exe")]
    public void ClientMustBeTheExpectedExecutableOfTheExpectedPackage(string relativePath)
    {
        Assert.True(PackagedPipeClient.IsExpected(Root + "\\" + relativePath, Family, Family, Root, relativePath));
        Assert.False(PackagedPipeClient.IsExpected(@"C:\Temp\attacker.exe", Family, Family, Root, relativePath));
        Assert.False(PackagedPipeClient.IsExpected(Root + "\\" + relativePath, "PanelDeControl.Windows_otherpublisher", Family, Root, relativePath));
    }

    [Fact]
    public void UnknownExpectedPackageTrustsNobody()
    {
        var path = Root + "\\" + PackagedWidgetClientValidator.WidgetRelativePath;
        Assert.False(PackagedPipeClient.IsExpected(path, Family, null, Root, PackagedWidgetClientValidator.WidgetRelativePath));
        Assert.False(PackagedPipeClient.IsExpected(path, null, null, Root, PackagedWidgetClientValidator.WidgetRelativePath));
    }
}
