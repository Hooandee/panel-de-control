using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

// Measured on a ROG Xbox Ally X (companion.log): Game Bar opened over chiaki-ng launched from Steam and closed again
// 375-430 ms later went Home; opened over the same game and left open 129754 ms did not.
public sealed class GameBarButtonPolicyTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 17, 18, 56, 20, TimeSpan.Zero);

    [Fact]
    public void OpeningAndClosingGameBarAtOnceOverAGameGoesHome()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420), Now, gameRunning: true));
    }

    [Fact]
    public void GameBarLeftOpenOverAGameIsGameBarsOwn()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(129754), Now, gameRunning: true));
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

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), Now, gameRunning: true));
    }

    [Fact]
    public void EachOpeningCountsOnce()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);
        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420), Now, gameRunning: true));

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(300), Now, gameRunning: true));
    }

    [Fact]
    public void GameBarClosingAsTheGameEndsIsNotTheButton()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), Now, gameRunning: false));
    }

    [Fact]
    public void GameBarClosedByTheWidgetsHomeButtonIsNotASecondPress()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);
        policy.ExplicitHome(Now);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), Now.AddMilliseconds(400), gameRunning: true));

        policy.Shown(GameBarButtonPolicy.OverGame);
        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420), Now.AddSeconds(5), gameRunning: true));
    }
}
