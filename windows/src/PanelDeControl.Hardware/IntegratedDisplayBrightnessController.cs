using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class IntegratedDisplayBrightnessController
    : IDisplayBrightnessController
{
    private const uint Lvds = 6;
    private const uint DisplayPortEmbedded = 11;
    private const uint UdiEmbedded = 13;
    private const uint Internal = 0x80000000;
    private const uint WmiSetTimeoutSeconds = 1;
    private const int ReadbackTolerancePercentagePoints = 1;

    private readonly IDisplayBrightnessProvider provider;

    public IntegratedDisplayBrightnessController(IDisplayBrightnessProvider provider)
    {
        this.provider = provider;
    }

    public BrightnessControlResponse Get()
    {
        var selection = SelectCapability();
        return selection.Failure ??
            BrightnessControlResponse.Available(
                selection.Capability!.CurrentBrightness);
    }

    public BrightnessControlResponse Set(int requestedPercentage)
    {
        if (!IsPercentage(requestedPercentage))
        {
            return BrightnessControlResponse.Rejected(
                "invalid_brightness_percentage");
        }

        var selection = SelectCapability();
        if (selection.Failure is not null)
        {
            return selection.Failure;
        }

        var capability = selection.Capability!;
        var targetPercentage = capability.Levels
            .Where(IsPercentage)
            .Distinct()
            .OrderBy(level => Math.Abs(level - requestedPercentage))
            .ThenBy(level => level)
            .First();

        uint result;
        try
        {
            result = provider.SetBrightness(
                capability.InstanceName,
                targetPercentage,
                WmiSetTimeoutSeconds);
        }
        catch (UnauthorizedAccessException)
        {
            return BrightnessControlResponse.PermissionRequired(
                "brightness_permission_required");
        }
        catch (BrightnessWriteInProgressException)
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_write_busy");
        }
        catch (TimeoutException)
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_control_timeout");
        }
        catch
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_write_failed");
        }

        if (result != 0)
        {
            return BrightnessControlResponse.Fault("brightness_set_failed");
        }

        int observedPercentage;
        try
        {
            observedPercentage = provider.ReadBrightness(
                capability.InstanceName);
        }
        catch (BrightnessReadInProgressException)
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_read_busy");
        }
        catch
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_readback_failed");
        }

        if (!IsPercentage(observedPercentage))
        {
            return BrightnessControlResponse.Unverifiable(
                targetPercentage,
                null,
                "brightness_readback_invalid");
        }

        return Math.Abs(observedPercentage - targetPercentage) <=
            ReadbackTolerancePercentagePoints
            ? BrightnessControlResponse.Applied(
                targetPercentage,
                observedPercentage)
            : BrightnessControlResponse.Unverifiable(
                targetPercentage,
                observedPercentage,
                "brightness_readback_mismatch");
    }

    private Selection SelectCapability()
    {
        IReadOnlyList<DisplayBrightnessCapability> discovered;
        try
        {
            discovered = provider.Discover();
        }
        catch (UnauthorizedAccessException)
        {
            return Selection.Failed(
                BrightnessControlResponse.PermissionRequired(
                    "brightness_permission_required"));
        }
        catch (BrightnessReadInProgressException)
        {
            return Selection.Failed(
                BrightnessControlResponse.Fault(
                    "brightness_read_busy"));
        }
        catch
        {
            return Selection.Failed(
                BrightnessControlResponse.Fault("brightness_provider_failed"));
        }

        var candidates = discovered
            .Where(IsControllableIntegratedDisplay)
            .ToArray();
        return candidates.Length switch
        {
            0 => Selection.Failed(
                BrightnessControlResponse.Unavailable(
                    "integrated_display_unavailable")),
            1 => Selection.Succeeded(candidates[0]),
            _ => Selection.Failed(
                BrightnessControlResponse.Unavailable(
                    "integrated_display_ambiguous")),
        };
    }

    private static bool IsControllableIntegratedDisplay(
        DisplayBrightnessCapability capability)
    {
        if (!capability.Active ||
            !capability.CanSet ||
            string.IsNullOrWhiteSpace(capability.InstanceName) ||
            !IsIntegrated(capability.VideoOutputTechnology))
        {
            return false;
        }

        var validLevels = capability.Levels
            .Where(IsPercentage)
            .ToArray();
        return validLevels.Length > 0 &&
            IsPercentage(capability.CurrentBrightness) &&
            validLevels.Contains(capability.CurrentBrightness);
    }

    private static bool IsIntegrated(uint videoOutputTechnology)
    {
        return videoOutputTechnology is
            Lvds or
            DisplayPortEmbedded or
            UdiEmbedded or
            Internal;
    }

    private static bool IsPercentage(int percentage)
    {
        return percentage >= 0 && percentage <= 100;
    }

    private sealed record Selection(
        DisplayBrightnessCapability? Capability,
        BrightnessControlResponse? Failure)
    {
        public static Selection Succeeded(
            DisplayBrightnessCapability capability)
        {
            return new Selection(capability, null);
        }

        public static Selection Failed(BrightnessControlResponse response)
        {
            return new Selection(null, response);
        }
    }
}
