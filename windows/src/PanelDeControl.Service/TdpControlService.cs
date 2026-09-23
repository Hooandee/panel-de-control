using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Devices;
using PanelDeControl.Hardware;
using PanelDeControl.Hardware.Capabilities;

namespace PanelDeControl.Service;

public enum AcPowerState
{
    Unknown,
    Battery,
    External,
}

public interface IAcPowerSource
{
    AcPowerState Read();
}

public interface IArmouryCrateGuard
{
    bool IsRunning();
}

public sealed class ArmouryCrateGuard : IArmouryCrateGuard
{
    private static readonly string[] ServiceNames =
    {
        "ArmouryCrateSEService",
        "AsusAppService",
        "ArmouryCrateControlInterface",
    };

    private readonly ISoftwareInventory inventory;

    public ArmouryCrateGuard(ISoftwareInventory inventory)
    {
        this.inventory = inventory;
    }

    public bool IsRunning()
    {
        try
        {
            return ServiceNames.Any(inventory.IsServiceRunning);
        }
        catch
        {
            return true;
        }
    }
}

public interface ITdpControlEndpoint
{
    TdpControlResponse Get();

    TdpControlResponse EnableExperimental();

    TdpControlResponse DisableExperimental();

    TdpControlResponse Set(int requestedWatts);
}

public sealed class TdpControlService : ITdpControlEndpoint
{
    private static readonly AsusTdpRegister[] Registers =
    {
        AsusTdpRegister.Pl1Spl,
        AsusTdpRegister.Sppt,
        AsusTdpRegister.Fppt,
    };

    private readonly object gate = new();
    private readonly IDeviceIdentityReader identityReader;
    private readonly IAcPowerSource powerSource;
    private readonly IArmouryCrateGuard armouryCrate;
    private readonly IAsusTdpTransport transport;
    private bool experimentalEnabled;

    public TdpControlService(
        IDeviceIdentityReader identityReader,
        IAcPowerSource powerSource,
        IArmouryCrateGuard armouryCrate,
        IAsusTdpTransport transport)
    {
        this.identityReader = identityReader;
        this.powerSource = powerSource;
        this.armouryCrate = armouryCrate;
        this.transport = transport;
    }

    public TdpControlResponse Get()
    {
        lock (gate)
        {
            return ReadAvailableState(manufacturerRecoveryUnverified: false);
        }
    }

    public TdpControlResponse EnableExperimental()
    {
        lock (gate)
        {
            var profile = ReadSupportedProfile();
            if (profile is null)
            {
                return TdpControlResponse.Unavailable(
                    experimentalEnabled,
                    "tdp_profile_unsupported");
            }

            experimentalEnabled = true;
            return ReadAvailableState(
                profile,
                manufacturerRecoveryUnverified: false);
        }
    }

    public TdpControlResponse DisableExperimental()
    {
        lock (gate)
        {
            experimentalEnabled = false;
            return ReadAvailableState(manufacturerRecoveryUnverified: true);
        }
    }

    public TdpControlResponse Set(int requestedWatts)
    {
        lock (gate)
        {
            var profile = ReadSupportedProfile();
            if (profile is null)
            {
                return TdpControlResponse.Unavailable(
                    experimentalEnabled,
                    "tdp_profile_unsupported");
            }

            if (!experimentalEnabled)
            {
                return RejectedBeforeWrite(
                    profile,
                    requestedWatts,
                    "experimental_tdp_disabled");
            }

            if (armouryCrate.IsRunning())
            {
                return RejectedBeforeWrite(
                    profile,
                    requestedWatts,
                    "armoury_crate_running");
            }

            var power = powerSource.Read();
            if (power == AcPowerState.Unknown)
            {
                return TdpControlResponse.Unavailable(
                    experimentalEnabled,
                    "power_source_unknown");
            }

            var target = TdpLimitPolicy.CreateTarget(
                profile,
                requestedWatts,
                power == AcPowerState.External);
            for (var index = 0; index < Registers.Length; index++)
            {
                var result = transport.Write(Registers[index], target.TargetWatts);
                if (result == AsusTdpWriteResult.Rejected)
                {
                    return index == 0
                        ? AttemptRejected(profile, target, "firmware_rejected")
                        : AttemptUnverifiable(
                            profile,
                            target,
                            "firmware_partially_applied");
                }

                if (result == AsusTdpWriteResult.Fault)
                {
                    return AttemptUnverifiable(
                        profile,
                        target,
                        "firmware_io_failed");
                }
            }

            var readbacks = Registers
                .Select(transport.Read)
                .ToArray();
            if (readbacks.Any(result => !result.HasValue))
            {
                return AttemptUnverifiable(
                    profile,
                    target,
                    "readback_unavailable");
            }

            if (readbacks.Any(result => result.Watts != target.TargetWatts))
            {
                return AttemptUnverifiable(
                    profile,
                    target,
                    "readback_mismatch");
            }

            return TdpControlResponse.Applied(
                experimentalEnabled,
                target.RequestedWatts,
                target.TargetWatts,
                target.TargetWatts,
                target.MinimumWatts,
                target.MaximumWatts,
                profile.Limits.TdpPresets,
                target.ExternalPower);
        }
    }

    private TdpControlResponse ReadAvailableState(
        bool manufacturerRecoveryUnverified)
    {
        var profile = ReadSupportedProfile();
        return profile is null
            ? TdpControlResponse.Unavailable(
                experimentalEnabled,
                "tdp_profile_unsupported")
            : ReadAvailableState(profile, manufacturerRecoveryUnverified);
    }

    private TdpControlResponse ReadAvailableState(
        DeviceProfile profile,
        bool manufacturerRecoveryUnverified)
    {
        var power = powerSource.Read();
        if (power == AcPowerState.Unknown)
        {
            return TdpControlResponse.Unavailable(
                experimentalEnabled,
                "power_source_unknown");
        }

        var external = power == AcPowerState.External;
        if (armouryCrate.IsRunning())
        {
            return TdpControlResponse.Rejected(
                experimentalEnabled,
                requestedWatts: null,
                targetWatts: null,
                profile.Limits.TdpMin,
                external
                    ? profile.Limits.TdpMaxCharger
                    : profile.Limits.TdpMax,
                profile.Limits.TdpPresets,
                external,
                "armoury_crate_running");
        }

        return TdpControlResponse.Available(
            experimentalEnabled,
            profile.Limits.TdpMin,
            external
                ? profile.Limits.TdpMaxCharger
                : profile.Limits.TdpMax,
            profile.Limits.TdpPresets,
            external,
            manufacturerRecoveryUnverified);
    }

    private DeviceProfile? ReadSupportedProfile()
    {
        var profile = identityReader.Read().Profile;
        return string.Equals(
            profile?.Key,
            TdpLimitPolicy.SupportedProfileKey,
            StringComparison.Ordinal)
            ? profile
            : null;
    }

    private TdpControlResponse RejectedBeforeWrite(
        DeviceProfile profile,
        int requestedWatts,
        string errorCode)
    {
        var power = powerSource.Read();
        bool? external = power == AcPowerState.Unknown
            ? null
            : power == AcPowerState.External;
        return TdpControlResponse.Rejected(
            experimentalEnabled,
            requestedWatts,
            null,
            profile.Limits.TdpMin,
            external == true
                ? profile.Limits.TdpMaxCharger
                : profile.Limits.TdpMax,
            profile.Limits.TdpPresets,
            external,
            errorCode);
    }

    private TdpControlResponse AttemptRejected(
        DeviceProfile profile,
        TdpTarget target,
        string errorCode)
    {
        return TdpControlResponse.Rejected(
            experimentalEnabled,
            target.RequestedWatts,
            target.TargetWatts,
            target.MinimumWatts,
            target.MaximumWatts,
            profile.Limits.TdpPresets,
            target.ExternalPower,
            errorCode);
    }

    private TdpControlResponse AttemptUnverifiable(
        DeviceProfile profile,
        TdpTarget target,
        string errorCode)
    {
        return TdpControlResponse.Unverifiable(
            experimentalEnabled,
            target.RequestedWatts,
            target.TargetWatts,
            target.MinimumWatts,
            target.MaximumWatts,
            profile.Limits.TdpPresets,
            target.ExternalPower,
            errorCode);
    }
}
