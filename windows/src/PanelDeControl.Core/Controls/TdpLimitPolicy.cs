using PanelDeControl.Core.Devices;

namespace PanelDeControl.Core.Controls;

public sealed class TdpTarget
{
    public TdpTarget(
        int requestedWatts,
        int targetWatts,
        int minimumWatts,
        int maximumWatts,
        bool externalPower)
    {
        RequestedWatts = requestedWatts;
        TargetWatts = targetWatts;
        MinimumWatts = minimumWatts;
        MaximumWatts = maximumWatts;
        ExternalPower = externalPower;
    }

    public int RequestedWatts { get; }

    public int TargetWatts { get; }

    public int MinimumWatts { get; }

    public int MaximumWatts { get; }

    public bool ExternalPower { get; }
}

public static class TdpLimitPolicy
{
    public const string SupportedProfileKey = "rog_xbox_ally_x";

    public static TdpTarget CreateTarget(
        DeviceProfile profile,
        int requestedWatts,
        bool externalPower)
    {
        if (profile is null)
        {
            throw new ArgumentNullException(nameof(profile));
        }
        if (!string.Equals(
                profile.Key,
                SupportedProfileKey,
                StringComparison.Ordinal))
        {
            throw new NotSupportedException(
                $"TDP writes are not enabled for {profile.Key}.");
        }

        var minimum = profile.Limits.TdpMin;
        var maximum = externalPower
            ? profile.Limits.TdpMaxCharger
            : profile.Limits.TdpMax;
        if (minimum < 0 || maximum < minimum)
        {
            throw new InvalidDataException("Catalog TDP limits are invalid.");
        }

        var target = Math.Min(Math.Max(requestedWatts, minimum), maximum);
        return new TdpTarget(
            requestedWatts,
            target,
            minimum,
            maximum,
            externalPower);
    }
}
