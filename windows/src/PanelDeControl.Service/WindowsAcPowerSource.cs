using System.Runtime.InteropServices;

namespace PanelDeControl.Service;

public sealed class WindowsAcPowerSource : IAcPowerSource
{
    public AcPowerState Read()
    {
        if (!OperatingSystem.IsWindows() ||
            !GetSystemPowerStatus(out var status))
        {
            return AcPowerState.Unknown;
        }

        return status.AcLineStatus switch
        {
            0 => AcPowerState.Battery,
            1 => AcPowerState.External,
            _ => AcPowerState.Unknown,
        };
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSystemPowerStatus(out SystemPowerStatus status);

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemPowerStatus
    {
        public byte AcLineStatus;
        public byte BatteryFlag;
        public byte BatteryLifePercent;
        public byte SystemStatusFlag;
        public int BatteryLifeTime;
        public int BatteryFullLifeTime;
    }
}
