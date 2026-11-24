using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

// Timings measured with Game Bar over a game: opened and closed again 375-430 ms later (two presses), left open
// 129754 ms (one press).
public sealed class GameBarButtonPolicyTests
{
    [Fact]
    public void OpeningAndClosingGameBarAtOnceOverAGameGoesHome()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420), gameRunning: true));
    }

    [Fact]
    public void GameBarLeftOpenOverAGameIsGameBarsOwn()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(129754), gameRunning: true));
    }

    [Theory]
    [InlineData("none")]
    [InlineData("inactive")]
    [InlineData("no_host")]
    [InlineData("unreachable")]
    public void OverBigPictureWithoutAGameOrATheme_TwoPressesDoNothing(string hostAnswer)
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(hostAnswer);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), gameRunning: true));
    }

    [Fact]
    public void EachOpeningCountsOnce()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);
        Assert.True(policy.Hidden(TimeSpan.FromMilliseconds(420), gameRunning: true));

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(300), gameRunning: true));
    }

    [Fact]
    public void GameBarClosingAsTheGameEndsIsNotTheButton()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), gameRunning: false));
    }

    [Fact]
    public void GameBarClosedByTheWidgetsHomeButtonIsNotASecondPress()
    {
        var policy = new GameBarButtonPolicy();

        policy.Shown(GameBarButtonPolicy.OverGame);
        policy.Forget();

        Assert.False(policy.Hidden(TimeSpan.FromMilliseconds(420), gameRunning: true));
    }
}
