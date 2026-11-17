namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// What the player had in front when Game Bar opened: Big Picture (Steam) or a game or app (Other). On the ROG Xbox
/// Ally X an open Game Bar leaves the shell's immersive window in the foreground, and it stays there after Game Bar
/// closes, so neither Game Bar nor the shell counts. When the companion itself brings a window up by window order,
/// Windows may keep reporting the other one in the foreground: what the player sees is noted, and that note lasts
/// until Windows reports Big Picture or a game in the foreground again.
/// </summary>
public sealed class GameBarForeground
{
    private readonly object gate = new();
    private ForegroundKind observed = ForegroundKind.Other;
    private ForegroundKind? noted;
    private bool bigPictureRaisedByOrder;
    private DateTimeOffset? bigPictureHeldSince;

    /// <summary>
    /// Closing Game Bar hands the game the foreground for a moment right after Big Picture was raised over it; only a
    /// return to the game seen after that counts as the player going back to it.
    /// </summary>
    public static readonly TimeSpan SettleAfterRaise = TimeSpan.FromSeconds(2);

    public void Observe(ForegroundKind kind)
    {
        if (kind is not (ForegroundKind.Steam or ForegroundKind.Other))
        {
            return;
        }

        lock (gate)
        {
            observed = kind;
            noted = null;
        }
    }

    public ForegroundKind BeforeGameBar(ForegroundKind current)
    {
        lock (gate)
        {
            return noted ?? (current is ForegroundKind.Steam or ForegroundKind.Other ? current : observed);
        }
    }

    /// <summary>Big Picture came Home over the game; <paramref name="byOrder"/> when it was brought up by window order.</summary>
    public void BigPictureRaised(bool byOrder)
    {
        lock (gate)
        {
            if (byOrder)
            {
                noted = ForegroundKind.Steam;
                bigPictureRaisedByOrder = true;
            }
        }
    }

    /// <summary>
    /// Steam resumed the game. Returns whether Big Picture had come over it by window order, the one case where
    /// Windows also refuses Steam's raise and the companion must raise the game itself.
    /// </summary>
    public bool GameResumed()
    {
        lock (gate)
        {
            noted = ForegroundKind.Other;
            var needed = bigPictureRaisedByOrder;
            bigPictureRaisedByOrder = false;
            return needed;
        }
    }

    /// <summary>No game runs any more: nothing raised for it still holds.</summary>
    /// <summary>Big Picture stays topmost over a full screen game from <paramref name="at"/>.</summary>
    public void BigPictureHeld(DateTimeOffset at)
    {
        lock (gate)
        {
            bigPictureHeldSince = at;
        }
    }

    /// <summary>
    /// A game or app took the foreground at <paramref name="at"/>. Returns whether Big Picture, held topmost over the
    /// game, must give way: the player went back to the game (Alt+Tab, Xbox's switcher) without Steam.
    /// </summary>
    public bool GameTookForeground(DateTimeOffset at)
    {
        lock (gate)
        {
            if (bigPictureHeldSince is not { } since || at - since < SettleAfterRaise)
            {
                return false;
            }

            bigPictureHeldSince = null;
            return true;
        }
    }

    /// <summary>Big Picture no longer holds a topmost place.</summary>
    public void BigPictureLet()
    {
        lock (gate)
        {
            bigPictureHeldSince = null;
        }
    }

    public void GameEnded()
    {
        lock (gate)
        {
            bigPictureRaisedByOrder = false;
            if (noted == ForegroundKind.Other)
            {
                noted = null;
            }
        }
    }
}
