using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class DeviceIdentityTests
{
    [Fact]
    public void EmbeddedCatalogLoads()
    {
        var catalog = DeviceCatalogResource.TryLoad();

        Assert.NotNull(catalog);
        Assert.NotEmpty(catalog!.Profiles);
    }

    [Theory]
    [InlineData("ASUSTeK COMPUTER INC.", "ROG Xbox Ally X RC73XA_RC73XA", "RC73XA", "rog_xbox_ally_x", "ROG Xbox Ally X")]
    [InlineData("LENOVO", "83E1", "", "legion_go", "Legion Go")]
    [InlineData("LENOVO", "83N0", "", "legion_go_2", "Legion Go 2")]
    [InlineData("Micro-Star International Co., Ltd.", "Claw 8 AI+ A2VM", "", "msi_claw_8_ai_plus", "MSI Claw 8 AI+")]
    public void WindowsFleetIsRecognizedFromTheSharedCatalog(
        string manufacturer,
        string model,
        string board,
        string expectedKey,
        string expectedName)
    {
        var identity = DeviceIdentity.FromDmi(DeviceCatalogResource.TryLoad(), manufacturer, model, board);

        Assert.True(identity.IsRecognized);
        Assert.Equal(expectedKey, identity.ProfileId);
        Assert.Equal(expectedName, identity.DisplayName);
        Assert.Equal(model, identity.ProductName);
    }

    [Fact]
    public void PreviousAllyXDoesNotMasqueradeAsXboxAllyX()
    {
        var identity = DeviceIdentity.FromDmi(
            DeviceCatalogResource.TryLoad(),
            "ASUSTeK COMPUTER INC.",
            "ROG Ally X RC72LA",
            "RC72LA");

        Assert.Equal("rog_ally_x", identity.ProfileId);
    }

    [Fact]
    public void UnknownDeviceKeepsItsRealNameAndStaysUnrecognized()
    {
        var identity = DeviceIdentity.FromDmi(
            DeviceCatalogResource.TryLoad(),
            "Contoso",
            "Some Laptop 15",
            "X1");

        Assert.False(identity.IsRecognized);
        Assert.Equal("unknown", identity.ProfileId);
        Assert.Equal("Some Laptop 15", identity.DisplayName);
    }

    [Fact]
    public void MissingCatalogFailsClosedToUnrecognized()
    {
        var identity = DeviceIdentity.FromDmi(null, "ASUSTeK COMPUTER INC.", "ROG Xbox Ally X", "RC73XA");

        Assert.False(identity.IsRecognized);
        Assert.Equal("ROG Xbox Ally X", identity.DisplayName);
    }

    [Fact]
    public void EmptyProductNameRemainsUnknown()
    {
        var identity = DeviceIdentity.FromDmi(DeviceCatalogResource.TryLoad(), "ASUSTeK COMPUTER INC.", " ", null);

        Assert.Equal("Unknown device", identity.ProductName);
        Assert.False(identity.IsRecognized);
    }
}
