using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class CompanionLaunchPolicyTests
{
    private static readonly DateTimeOffset Start = new(2026, 10, 20, 2, 0, 0, TimeSpan.Zero);

    [Fact]
    public void LaunchesOnlyWhenSteamRunsWithoutTheCompanion()
    {
        var policy = new CompanionLaunchPolicy();

        Assert.False(policy.ShouldLaunch(steamRunning: false, companionRunning: false, Start));
        Assert.False(policy.ShouldLaunch(steamRunning: true, companionRunning: true, Start));
        Assert.True(policy.ShouldLaunch(steamRunning: true, companionRunning: false, Start));
    }

    [Fact]
    public void WaitsAMinuteBetweenAttempts()
    {
        var policy = new CompanionLaunchPolicy();
        Assert.True(policy.ShouldLaunch(true, false, Start));

        Assert.False(policy.ShouldLaunch(true, false, Start.AddSeconds(30)));
        Assert.True(policy.ShouldLaunch(true, false, Start + CompanionLaunchPolicy.MinimumGap));
    }
}
