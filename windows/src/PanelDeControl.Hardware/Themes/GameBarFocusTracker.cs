namespace PanelDeControl.Hardware.Themes;

public enum ForegroundKind
{
    Steam,
    GameBar,
    Shell,
    Other,
}

public sealed record ForegroundWindow(IntPtr Handle, ForegroundKind Kind);

/// <summary>
/// Over a full screen Big Picture, Windows can leave the foreground on the desktop (after Game Bar
/// or a touch on one of its widgets), and Steam themes pause while their window has no focus. Focus
/// goes back only when Big Picture covered the screen and nothing but the shell or Game Bar took it.
/// </summary>
public sealed class GameBarFocusTracker
{
    private IntPtr lastSteam;
    private bool overlayOverSteam;

    /// <summary>Returns the Steam window to restore, or zero.</summary>
    public IntPtr Observe(ForegroundWindow current)
    {
        switch (current.Kind)
        {
            case ForegroundKind.Steam:
                lastSteam = current.Handle;
                overlayOverSteam = false;
                return IntPtr.Zero;
            case ForegroundKind.GameBar:
                overlayOverSteam |= lastSteam != IntPtr.Zero;
                return IntPtr.Zero;
            case ForegroundKind.Shell when overlayOverSteam || lastSteam != IntPtr.Zero:
                overlayOverSteam = false;
                var restore = lastSteam;
                lastSteam = IntPtr.Zero;
                return restore;
            default:
                overlayOverSteam = false;
                lastSteam = current.Kind == ForegroundKind.Other ? IntPtr.Zero : lastSteam;
                return IntPtr.Zero;
        }
    }
}
