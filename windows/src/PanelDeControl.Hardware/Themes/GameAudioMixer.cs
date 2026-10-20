using System.Runtime.InteropServices;

namespace PanelDeControl.Hardware.Themes;

public interface IGameAudioMixer
{
    /// <summary>Every app session on every active output, held until the scan is disposed.</summary>
    IGameAudioScan Scan(IReadOnlyDictionary<int, ProcessEntry> processes);

    IReadOnlyDictionary<int, ProcessEntry> Processes();
}

public interface IGameAudioScan : IDisposable
{
    IReadOnlyList<AudioSessionState> Sessions { get; }

    void SetMute(int index, bool muted);
}

/// <summary>Windows' per-app mixer (Core Audio sessions), the same one the volume mixer shows.</summary>
public sealed class CoreAudioGameMixer : IGameAudioMixer
{
    private const uint ClassContextAll = 23;
    private const uint DeviceStateActive = 1;
    private const int RenderFlow = 0;

    public IGameAudioScan Scan(IReadOnlyDictionary<int, ProcessEntry> processes)
    {
        var scan = new CoreAudioScan(processes);
        var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
        try
        {
            Marshal.ThrowExceptionForHR(enumerator.EnumAudioEndpoints(RenderFlow, DeviceStateActive, out var devices));
            try
            {
                Marshal.ThrowExceptionForHR(devices.GetCount(out var deviceCount));
                for (uint deviceIndex = 0; deviceIndex < deviceCount; deviceIndex++)
                {
                    if (devices.Item(deviceIndex, out var device) != 0)
                    {
                        continue;
                    }

                    try
                    {
                        scan.AddDevice(device);
                    }
                    finally
                    {
                        Release(device);
                    }
                }
            }
            finally
            {
                Release(devices);
            }

            return scan;
        }
        catch
        {
            scan.Dispose();
            throw;
        }
        finally
        {
            Release(enumerator);
        }
    }

    public IReadOnlyDictionary<int, ProcessEntry> Processes()
    {
        var processes = new Dictionary<int, ProcessEntry>();
        var snapshot = CreateToolhelp32Snapshot(SnapProcess, 0);
        if (snapshot == InvalidHandle)
        {
            return processes;
        }

        try
        {
            var entry = new ProcessEntry32 { dwSize = (uint)Marshal.SizeOf<ProcessEntry32>() };
            for (var more = Process32FirstW(snapshot, ref entry); more; more = Process32NextW(snapshot, ref entry))
            {
                processes[(int)entry.th32ProcessID] = new ProcessEntry((int)entry.th32ParentProcessID, entry.szExeFile);
            }
        }
        finally
        {
            CloseHandle(snapshot);
        }

        return processes;
    }

    private static void Release(object? instance)
    {
        if (instance is not null && Marshal.IsComObject(instance))
        {
            Marshal.FinalReleaseComObject(instance);
        }
    }

    private sealed class CoreAudioScan : IGameAudioScan
    {
        private readonly List<AudioSessionState> sessions = new();
        private readonly List<ISimpleAudioVolume> volumes = new();
        private readonly IReadOnlyDictionary<int, ProcessEntry> processes;

        public CoreAudioScan(IReadOnlyDictionary<int, ProcessEntry> processes)
        {
            this.processes = processes;
        }

        public IReadOnlyList<AudioSessionState> Sessions => sessions;

        public void AddDevice(IMMDevice device)
        {
            var managerId = typeof(IAudioSessionManager2).GUID;
            if (device.Activate(ref managerId, ClassContextAll, IntPtr.Zero, out var managerObject) != 0)
            {
                return;
            }

            var manager = (IAudioSessionManager2)managerObject;
            try
            {
                if (manager.GetSessionEnumerator(out var enumerator) != 0)
                {
                    return;
                }

                try
                {
                    enumerator.GetCount(out var count);
                    for (var index = 0; index < count; index++)
                    {
                        if (enumerator.GetSession(index, out var control) == 0)
                        {
                            AddSession(control);
                        }
                    }
                }
                finally
                {
                    Release(enumerator);
                }
            }
            finally
            {
                Release(manager);
            }
        }

        private void AddSession(IAudioSessionControl control)
        {
            var keep = false;
            try
            {
                var details = (IAudioSessionControl2)control;
                // IsSystemSoundsSession answers S_OK (0) for the system sounds session.
                if (details.IsSystemSoundsSession() == 0 || details.GetProcessId(out var processId) != 0 || processId == 0)
                {
                    return;
                }

                var volume = (ISimpleAudioVolume)control;
                if (volume.GetMute(out var muted) != 0)
                {
                    return;
                }

                sessions.Add(new AudioSessionState((int)processId, Executable((int)processId), muted));
                volumes.Add(volume);
                keep = true;
            }
            catch (InvalidCastException)
            {
            }
            finally
            {
                if (!keep)
                {
                    Release(control);
                }
            }
        }

        private string Executable(int processId) =>
            processes.TryGetValue(processId, out var entry) ? entry.Executable : $"pid-{processId}";

        public void SetMute(int index, bool muted)
        {
            var context = Guid.Empty;
            Marshal.ThrowExceptionForHR(volumes[index].SetMute(muted, ref context));
        }

        public void Dispose()
        {
            foreach (var volume in volumes)
            {
                Release(volume);
            }

            volumes.Clear();
            sessions.Clear();
        }
    }

    private const uint SnapProcess = 0x00000002;
    private static readonly IntPtr InvalidHandle = new(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct ProcessEntry32
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint processId);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Process32FirstW(IntPtr snapshot, ref ProcessEntry32 entry);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Process32NextW(IntPtr snapshot, ref ProcessEntry32 entry);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    [ComImport]
    [Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    private class MMDeviceEnumeratorComObject
    {
    }

    // COM interop does not inherit interfaces: every vtable slot is declared in order, unused ones included.
    [ComImport]
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDeviceEnumerator
    {
        [PreserveSig] int EnumAudioEndpoints(int dataFlow, uint stateMask, out IMMDeviceCollection devices);
        [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
        [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IMMDevice device);
        [PreserveSig] int RegisterEndpointNotificationCallback(IntPtr client);
        [PreserveSig] int UnregisterEndpointNotificationCallback(IntPtr client);
    }

    [ComImport]
    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDeviceCollection
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int Item(uint index, out IMMDevice device);
    }

    [ComImport]
    [Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDevice
    {
        [PreserveSig] int Activate(ref Guid interfaceId, uint classContext, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object instance);
        [PreserveSig] int OpenPropertyStore(uint access, out IntPtr properties);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetState(out uint state);
    }

    [ComImport]
    [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioSessionManager2
    {
        [PreserveSig] int GetAudioSessionControl(IntPtr sessionGuid, uint flags, out IntPtr control);
        [PreserveSig] int GetSimpleAudioVolume(IntPtr sessionGuid, uint flags, out IntPtr volume);
        [PreserveSig] int GetSessionEnumerator(out IAudioSessionEnumerator enumerator);
        [PreserveSig] int RegisterSessionNotification(IntPtr notification);
        [PreserveSig] int UnregisterSessionNotification(IntPtr notification);
        [PreserveSig] int RegisterDuckNotification([MarshalAs(UnmanagedType.LPWStr)] string sessionId, IntPtr notification);
        [PreserveSig] int UnregisterDuckNotification(IntPtr notification);
    }

    [ComImport]
    [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioSessionEnumerator
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetSession(int index, out IAudioSessionControl session);
    }

    [ComImport]
    [Guid("F4B1A599-7266-4319-A8CA-E70ACB11E8CD")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioSessionControl
    {
        [PreserveSig] int GetState(out int state);
    }

    [ComImport]
    [Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioSessionControl2
    {
        [PreserveSig] int GetState(out int state);
        [PreserveSig] int GetDisplayName(out IntPtr name);
        [PreserveSig] int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string name, ref Guid eventContext);
        [PreserveSig] int GetIconPath(out IntPtr path);
        [PreserveSig] int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string path, ref Guid eventContext);
        [PreserveSig] int GetGroupingParam(out Guid groupingParam);
        [PreserveSig] int SetGroupingParam(ref Guid groupingParam, ref Guid eventContext);
        [PreserveSig] int RegisterAudioSessionNotification(IntPtr notification);
        [PreserveSig] int UnregisterAudioSessionNotification(IntPtr notification);
        [PreserveSig] int GetSessionIdentifier(out IntPtr identifier);
        [PreserveSig] int GetSessionInstanceIdentifier(out IntPtr identifier);
        [PreserveSig] int GetProcessId(out uint processId);
        [PreserveSig] int IsSystemSoundsSession();
        [PreserveSig] int SetDuckingPreference([MarshalAs(UnmanagedType.Bool)] bool optOut);
    }

    [ComImport]
    [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ISimpleAudioVolume
    {
        [PreserveSig] int SetMasterVolume(float level, ref Guid eventContext);
        [PreserveSig] int GetMasterVolume(out float level);
        [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool muted, ref Guid eventContext);
        [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool muted);
    }
}
