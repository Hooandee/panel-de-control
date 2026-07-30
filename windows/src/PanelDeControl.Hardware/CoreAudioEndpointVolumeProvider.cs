using System.Runtime.InteropServices;

namespace PanelDeControl.Hardware;

public sealed class CoreAudioEndpointVolumeProvider : IAudioEndpointVolumeProvider
{
    private const uint ClassContextAll = 23;

    public IAudioEndpointVolumeSession OpenDefaultRenderEndpoint()
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException();
        }

        var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
        IMMDevice? endpointDevice = null;
        object? endpointVolumeObject = null;
        try
        {
            Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(
                DataFlow.Render,
                Role.Console,
                out var resolvedEndpoint));
            endpointDevice = resolvedEndpoint;

            var endpointVolumeInterface = typeof(IAudioEndpointVolume).GUID;
            Marshal.ThrowExceptionForHR(endpointDevice.Activate(
                ref endpointVolumeInterface,
                ClassContextAll,
                IntPtr.Zero,
                out endpointVolumeObject));

            return new CoreAudioEndpointVolumeSession(
                (IAudioEndpointVolume)endpointVolumeObject,
                endpointDevice);
        }
        catch
        {
            ReleaseComObject(endpointVolumeObject);
            ReleaseComObject(endpointDevice);
            throw;
        }
        finally
        {
            ReleaseComObject(enumerator);
        }
    }

    private static void ReleaseComObject(object? instance)
    {
        if (OperatingSystem.IsWindows() &&
            instance is not null &&
            Marshal.IsComObject(instance))
        {
            Marshal.FinalReleaseComObject(instance);
        }
    }

    private sealed class CoreAudioEndpointVolumeSession :
        IAudioEndpointVolumeSession
    {
        private IAudioEndpointVolume? endpointVolume;
        private IMMDevice? endpointDevice;

        public CoreAudioEndpointVolumeSession(
            IAudioEndpointVolume endpointVolume,
            IMMDevice endpointDevice)
        {
            this.endpointVolume = endpointVolume;
            this.endpointDevice = endpointDevice;
        }

        public double GetMasterVolumeLevel()
        {
            var volume = endpointVolume ?? throw new ObjectDisposedException(
                nameof(CoreAudioEndpointVolumeSession));
            Marshal.ThrowExceptionForHR(
                volume.GetMasterVolumeLevelScalar(out var level));
            return level;
        }

        public void SetMasterVolumeLevel(double requestedLevel)
        {
            var volume = endpointVolume ?? throw new ObjectDisposedException(
                nameof(CoreAudioEndpointVolumeSession));
            Marshal.ThrowExceptionForHR(
                volume.SetMasterVolumeLevelScalar(
                    (float)requestedLevel,
                    IntPtr.Zero));
        }

        public bool GetMute()
        {
            var volume = endpointVolume ?? throw new ObjectDisposedException(
                nameof(CoreAudioEndpointVolumeSession));
            Marshal.ThrowExceptionForHR(volume.GetMute(out var muted));
            return muted;
        }

        public void SetMute(bool requestedMuted)
        {
            var volume = endpointVolume ?? throw new ObjectDisposedException(
                nameof(CoreAudioEndpointVolumeSession));
            Marshal.ThrowExceptionForHR(volume.SetMute(requestedMuted, IntPtr.Zero));
        }

        public void Dispose()
        {
            ReleaseComObject(endpointVolume);
            endpointVolume = null;
            ReleaseComObject(endpointDevice);
            endpointDevice = null;
        }
    }

    private enum DataFlow
    {
        Render = 0,
    }

    private enum Role
    {
        Console = 0,
    }

    [ComImport]
    [Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    private class MMDeviceEnumeratorComObject
    {
    }

    [ComImport]
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDeviceEnumerator
    {
        [PreserveSig]
        int EnumAudioEndpoints(
            DataFlow dataFlow,
            uint stateMask,
            out IntPtr devices);

        [PreserveSig]
        int GetDefaultAudioEndpoint(
            DataFlow dataFlow,
            Role role,
            out IMMDevice endpoint);

        [PreserveSig]
        int GetDevice(
            [MarshalAs(UnmanagedType.LPWStr)] string id,
            out IMMDevice device);

        [PreserveSig]
        int RegisterEndpointNotificationCallback(IntPtr client);

        [PreserveSig]
        int UnregisterEndpointNotificationCallback(IntPtr client);
    }

    [ComImport]
    [Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDevice
    {
        [PreserveSig]
        int Activate(
            ref Guid interfaceId,
            uint classContext,
            IntPtr activationParameters,
            [MarshalAs(UnmanagedType.IUnknown)] out object activatedInterface);

        [PreserveSig]
        int OpenPropertyStore(uint access, out IntPtr properties);

        [PreserveSig]
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);

        [PreserveSig]
        int GetState(out uint state);
    }

    // Method order and signatures must match the Endpointvolume.h COM vtable.
    [ComImport]
    [Guid("5CDF2C82-841E-4546-9722-0CF74078229A")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioEndpointVolume
    {
        [PreserveSig]
        int RegisterControlChangeNotify(IntPtr notify);

        [PreserveSig]
        int UnregisterControlChangeNotify(IntPtr notify);

        [PreserveSig]
        int GetChannelCount(out uint channelCount);

        [PreserveSig]
        int SetMasterVolumeLevel(float level, IntPtr eventContext);

        [PreserveSig]
        int SetMasterVolumeLevelScalar(float level, IntPtr eventContext);

        [PreserveSig]
        int GetMasterVolumeLevel(out float level);

        [PreserveSig]
        int GetMasterVolumeLevelScalar(out float level);

        [PreserveSig]
        int SetChannelVolumeLevel(
            uint channelNumber,
            float level,
            IntPtr eventContext);

        [PreserveSig]
        int SetChannelVolumeLevelScalar(
            uint channelNumber,
            float level,
            IntPtr eventContext);

        [PreserveSig]
        int GetChannelVolumeLevel(uint channelNumber, out float level);

        [PreserveSig]
        int GetChannelVolumeLevelScalar(uint channelNumber, out float level);

        [PreserveSig]
        int SetMute(
            [MarshalAs(UnmanagedType.Bool)] bool muted,
            IntPtr eventContext);

        [PreserveSig]
        int GetMute([MarshalAs(UnmanagedType.Bool)] out bool muted);

        [PreserveSig]
        int GetVolumeStepInfo(out uint step, out uint stepCount);

        [PreserveSig]
        int VolumeStepUp(IntPtr eventContext);

        [PreserveSig]
        int VolumeStepDown(IntPtr eventContext);

        [PreserveSig]
        int QueryHardwareSupport(out uint hardwareSupportMask);

        [PreserveSig]
        int GetVolumeRange(
            out float minimumDecibels,
            out float maximumDecibels,
            out float incrementDecibels);
    }
}
