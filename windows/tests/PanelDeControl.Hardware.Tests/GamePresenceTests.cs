using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class GamePresenceTests
{
    [Fact]
    public void AGameEndsAfterTwoReadingsWithoutIt()
    {
        var presence = new GamePresence();

        Assert.Equal(GamePresenceChange.None, presence.Read(true));
        Assert.Equal(GamePresenceChange.None, presence.Read(false));
        Assert.Equal(GamePresenceChange.Ended, presence.Read(false));
        Assert.Equal(GamePresenceChange.None, presence.Read(false));
    }

    [Fact]
    public void OneMissedReadingIsNotAnEndNorANewStart()
    {
        var presence = new GamePresence();

        presence.Read(true);
        Assert.Equal(GamePresenceChange.None, presence.Read(false));
        Assert.Equal(GamePresenceChange.None, presence.Read(true));
    }

    [Fact]
    public void AGameStartsOnlyAfterSteamRanNone()
    {
        var presence = new GamePresence();

        presence.Read(false);
        presence.Read(false);

        Assert.Equal(GamePresenceChange.Started, presence.Read(true));
        Assert.Equal(GamePresenceChange.None, presence.Read(true));
    }

    [Fact]
    public void WithoutTheHostNothingChanges()
    {
        var presence = new GamePresence();
        presence.Read(true);

        Assert.Equal(GamePresenceChange.None, presence.Read(null));
        Assert.Equal(GamePresenceChange.None, presence.Read(null));
        Assert.Equal(GamePresenceChange.None, presence.Read(null));
        Assert.Equal(GamePresenceChange.None, presence.Read(true));
    }
}
