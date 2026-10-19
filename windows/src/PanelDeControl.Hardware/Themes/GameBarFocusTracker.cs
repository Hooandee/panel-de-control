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
/// Windows hands the foreground to the desktop, not back to Steam, when Game Bar closes over Big
/// Picture, and Steam themes pause while their window has no focus. This decides when focus should
/// go back: only when Game Bar opened over Steam and nothing else took its place.
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
            case ForegroundKind.Shell when overlayOverSteam:
                overlayOverSteam = false;
                return lastSteam;
            default:
                overlayOverSteam = false;
                lastSteam = current.Kind == ForegroundKind.Other ? IntPtr.Zero : lastSteam;
                return IntPtr.Zero;
        }
    }
}
