using System.Runtime.InteropServices;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public sealed class CoreAudioVolumeController : ISystemVolumeController
{
    private const int HResultEndpointNotFound = unchecked((int)0x80070490);

    private readonly IAudioEndpointVolumeProvider endpointProvider;

    public CoreAudioVolumeController(IAudioEndpointVolumeProvider endpointProvider)
    {
        this.endpointProvider = endpointProvider;
    }

    public VolumeControlResponse Get()
    {
        try
        {
            using var endpoint = endpointProvider.OpenDefaultRenderEndpoint();
            return VolumeControlResponse.Available(endpoint.GetMasterVolumeLevel());
        }
        catch (COMException exception) when (exception.HResult == HResultEndpointNotFound)
        {
            return VolumeControlResponse.Unavailable("audio_endpoint_unavailable");
        }
        catch (UnauthorizedAccessException)
        {
            return VolumeControlResponse.PermissionRequired("audio_permission_required");
        }
        catch
        {
            return VolumeControlResponse.Fault("volume_provider_failed");
        }
    }

    public VolumeControlResponse Set(double requestedLevel)
    {
        if (double.IsNaN(requestedLevel) ||
            double.IsInfinity(requestedLevel) ||
            requestedLevel < 0 ||
            requestedLevel > 1)
        {
            return VolumeControlResponse.Rejected("invalid_volume_level");
        }

        IAudioEndpointVolumeSession endpoint;
        try
        {
            endpoint = endpointProvider.OpenDefaultRenderEndpoint();
        }
        catch (COMException exception) when (exception.HResult == HResultEndpointNotFound)
        {
            return VolumeControlResponse.Unavailable("audio_endpoint_unavailable");
        }
        catch (UnauthorizedAccessException)
        {
            return VolumeControlResponse.PermissionRequired("audio_permission_required");
        }
        catch
        {
            return VolumeControlResponse.Fault("volume_provider_failed");
        }

        using (endpoint)
        {
            try
            {
                endpoint.SetMasterVolumeLevel(requestedLevel);
            }
            catch (UnauthorizedAccessException)
            {
                return VolumeControlResponse.PermissionRequired("audio_permission_required");
            }
            catch
            {
                return VolumeControlResponse.Fault("volume_provider_failed");
            }

            return ReadBack(endpoint, requestedLevel);
        }
    }

    private static VolumeControlResponse ReadBack(
        IAudioEndpointVolumeSession endpoint,
        double requestedLevel)
    {
        double observedLevel;
        try
        {
            observedLevel = endpoint.GetMasterVolumeLevel();
        }
        catch
        {
            return VolumeControlResponse.Unverifiable(
                requestedLevel,
                null,
                "volume_readback_failed");
        }

        return Math.Abs(observedLevel - requestedLevel) <= 0.01
            ? VolumeControlResponse.Applied(requestedLevel, observedLevel)
            : VolumeControlResponse.Unverifiable(
                requestedLevel,
                observedLevel,
                "volume_readback_mismatch");
    }
}
