using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class DeviceIdentityTests
{
    [Fact]
    public void ExactXboxAllyXProductIsRecognized()
    {
        var identity = DeviceIdentity.FromDmi(
            "ASUSTeK COMPUTER INC.",
            "ROG Xbox Ally X RC73XA_RC73XA");

        Assert.Equal("rog_xbox_ally_x", identity.ProfileId);
        Assert.True(identity.IsInitialTarget);
        Assert.Equal("ROG Xbox Ally X RC73XA_RC73XA", identity.ProductName);
    }

    [Fact]
    public void PreviousAllyXDoesNotMasqueradeAsXboxAllyX()
    {
        var identity = DeviceIdentity.FromDmi(
            "ASUSTeK COMPUTER INC.",
            "ROG Ally X RC72LA");

        Assert.Equal("unknown", identity.ProfileId);
        Assert.False(identity.IsInitialTarget);
    }

    [Fact]
    public void EmptyProductNameRemainsUnknown()
    {
        var identity = DeviceIdentity.FromDmi("ASUSTeK COMPUTER INC.", " ");

        Assert.Equal("Unknown device", identity.ProductName);
        Assert.Equal("unknown", identity.ProfileId);
        Assert.False(identity.IsInitialTarget);
    }
}
