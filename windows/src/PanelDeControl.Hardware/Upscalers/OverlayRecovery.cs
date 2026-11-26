namespace PanelDeControl.Hardware.Upscalers;

/// <summary>When the badge window may be created again after it failed: a few retries, a pause between them.</summary>
public sealed class OverlayBackoff
{
    public static readonly TimeSpan Delay = TimeSpan.FromSeconds(30);
    public const int MaxFailures = 4;

    private readonly object gate = new();
    private readonly HashSet<string> logged = new(StringComparer.Ordinal);
    private int failures;
    private DateTimeOffset retryAt = DateTimeOffset.MinValue;

    public bool CanStart(DateTimeOffset now)
    {
        lock (gate)
        {
            return failures < MaxFailures && now >= retryAt;
        }
    }

    /// <returns>True the first time this kind of failure happens: the only time it is worth logging.</returns>
    public bool Failed(DateTimeOffset now, string kind)
    {
        lock (gate)
        {
            failures++;
            retryAt = now + Delay;
            return logged.Add(kind);
        }
    }
}

public static class OverlayZOrder
{
    private const int WalkLimit = 4096;

    /// <summary>True when the game window sits above the badge, so the badge has to be raised again.</summary>
    /// <param name="above">The window directly above the given one, or zero.</param>
    public static bool GameIsAbove(IntPtr badge, IntPtr game, Func<IntPtr, IntPtr> above)
    {
        if (game == IntPtr.Zero)
        {
            return false;
        }

        var window = above(badge);
        for (var steps = 0; window != IntPtr.Zero && steps < WalkLimit; steps++)
        {
            if (window == game)
            {
                return true;
            }

            window = above(window);
        }

        return false;
    }
}
