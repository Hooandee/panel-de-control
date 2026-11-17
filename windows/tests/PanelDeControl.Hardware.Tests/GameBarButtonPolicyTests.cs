using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

// Measured on a ROG Xbox Ally X (companion.log): Game Bar opened over chiaki-ng launched from Steam and closed again
// 420 ms later went Home; opened over the same game and left open 129754 ms did not.
public sealed class GameBarButtonPolicyTests
{
    [Fact]
    public void OpeningAndClosingGameBarAtOnceOverAGameGoesHome()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420)));
    }

    [Fact]
    public void GameBarLeftOpenOverAGameIsGameBarsOwn()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(129754)));
    }

    [Theory]
    [InlineData("scheduled")]
    [InlineData("inactive")]
    [InlineData("no_host")]
    [InlineData("unreachable")]
    public void OverBigPictureOrWithoutATheme_OpeningWasAlreadyTheButton(string hostAnswer)
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(hostAnswer);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420)));
    }

    [Fact]
    public void EachOpeningCountsOnce()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);
        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420)));

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(300)));
    }
}
