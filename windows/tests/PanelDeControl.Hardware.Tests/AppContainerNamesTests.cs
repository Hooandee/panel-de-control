using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class AppContainerNamesTests
{
    [Theory]
    [InlineData("PanelDeControl.Windows_12cj5f9qay68w")]
    [InlineData("paneldecontrol.windows_12cj5f9qay68w")]
    public void SidMatchesWhatWindowsDerivesForThePackage(string familyName)
    {
        Assert.Equal(
            "S-1-15-2-3168518396-208711810-1087748364-2196912560-1336835272-3270088628-2842597931",
            AppContainerNames.SidFromPackageFamilyName(familyName));
    }

    [Fact]
    public void LocalPipesMoveIntoTheAppContainerNamespace()
    {
        Assert.Equal(
            @"Sessions\1\AppContainerNamedObjects\S-1-15-2-1\PanelDeControl.Telemetry",
            AppContainerNames.ServerPipeName(@"LOCAL\PanelDeControl.Telemetry", 1, "S-1-15-2-1"));
    }

    [Fact]
    public void GlobalPipesKeepTheirName()
    {
        Assert.Equal("PanelDeControl.Service", AppContainerNames.ServerPipeName("PanelDeControl.Service", 1, "S-1-15-2-1"));
    }

    [Fact]
    public void EmptyFamilyNameIsRejected()
    {
        Assert.Throws<ArgumentException>(() => AppContainerNames.SidFromPackageFamilyName(" "));
    }
}
