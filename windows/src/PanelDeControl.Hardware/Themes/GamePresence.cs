namespace PanelDeControl.Hardware.Themes;

public enum GamePresenceChange
{
    None,
    Started,
    Ended,
}

/// <summary>
/// Whether Steam runs a game, from the theme host's readings every couple of seconds. A reading without the host says
/// nothing; a game counts as ended after two readings without it, since one failed read also reports no game.
/// </summary>
public sealed class GamePresence
{
    private int readingsWithoutGame;

    /// <param name="gameRunning">The host's reading, or null when the host could not be read.</param>
    public GamePresenceChange Read(bool? gameRunning)
    {
        if (gameRunning is null)
        {
            return GamePresenceChange.None;
        }

        if (gameRunning.Value)
        {
            var started = readingsWithoutGame >= 2;
            readingsWithoutGame = 0;
            return started ? GamePresenceChange.Started : GamePresenceChange.None;
        }

        readingsWithoutGame++;
        return readingsWithoutGame == 2 ? GamePresenceChange.Ended : GamePresenceChange.None;
    }
}
