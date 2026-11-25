namespace PanelDeControl.Service;

/// <summary>
/// The Xbox full screen experience does not run startup apps, so the themes companion would stay
/// down until Game Bar is opened. The service starts it in the console session as soon as Steam is
/// there without it, at most once a minute.
/// </summary>
public sealed class CompanionLaunchPolicy
{
    public static readonly TimeSpan MinimumGap = TimeSpan.FromMinutes(1);

    private DateTimeOffset? lastLaunch;

    public bool ShouldLaunch(bool steamRunning, bool companionRunning, DateTimeOffset now)
    {
        if (!steamRunning || companionRunning || (lastLaunch is { } last && now - last < MinimumGap))
        {
            return false;
        }

        lastLaunch = now;
        return true;
    }
}
