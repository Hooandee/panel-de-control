namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Where Windows keeps the Xbox button for Game Bar, Game Bar opening over a running game is left to Game Bar (TDP,
/// Panel's widget). Pressing the button twice in a row opens and closes Game Bar at once: that is Steam's button over
/// the game, Big Picture's Home.
/// </summary>
public sealed class GameBarButtonPolicy
{
    /// <summary>The theme host's answer when Game Bar opened over a running game and it stood down.</summary>
    public const string OverGame = "game";

    public static readonly TimeSpan DoublePress = TimeSpan.FromMilliseconds(1000);

    private readonly object gate = new();
    private bool shownOverGame;

    /// <summary>Records what the theme host answered to Game Bar opening.</summary>
    public void Shown(string hostAnswer)
    {
        lock (gate)
        {
            shownOverGame = hostAnswer == OverGame;
        }
    }

    /// <summary>Whether Game Bar closing after being shown this long asks for Big Picture's Home over the game.</summary>
    public bool Hidden(TimeSpan shownFor)
    {
        lock (gate)
        {
            var overGame = shownOverGame;
            shownOverGame = false;
            return overGame && shownFor < DoublePress;
        }
    }
}
