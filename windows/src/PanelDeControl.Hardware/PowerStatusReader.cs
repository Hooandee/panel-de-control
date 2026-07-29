using System.Runtime.InteropServices;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public readonly record struct NativePowerStatus(
    byte AcLineStatus,
    byte BatteryLifePercent);

public sealed class PowerStatusReader : IPowerStatusReader
{
    public IReadOnlyList<TelemetryReading> Read()
    {
        if (!OperatingSystem.IsWindows())
        {
            return Unavailable(ReadingStatus.Unavailable, "power_windows_only");
        }

        if (!GetSystemPowerStatus(out var status))
        {
            return Unavailable(ReadingStatus.Fault, "power_status_failed");
        }

        return Map(new NativePowerStatus(status.AcLineStatus, status.BatteryLifePercent));
    }

    public static IReadOnlyList<TelemetryReading> Map(NativePowerStatus status)
    {
        var battery = status.BatteryLifePercent > 100
            ? TelemetryReading.Unavailable(
                "battery.level",
                "Batería",
                "%",
                ReadingStatus.Unavailable,
                "power_state_unknown")
            : TelemetryReading.Available(
                "battery.level",
                "Batería",
                status.BatteryLifePercent,
                "%",
                "win32/GetSystemPowerStatus");
        var ac = status.AcLineStatus > 1
            ? TelemetryReading.Unavailable(
                "power.ac",
                "Alimentación",
                "bool",
                ReadingStatus.Unavailable,
                "power_state_unknown")
            : TelemetryReading.Available(
                "power.ac",
                "Alimentación",
                status.AcLineStatus,
                "bool",
                "win32/GetSystemPowerStatus");

        return new[] { battery, ac };
    }

    private static IReadOnlyList<TelemetryReading> Unavailable(
        ReadingStatus status,
        string errorCode)
    {
        return new[]
        {
            TelemetryReading.Unavailable(
                "battery.level",
                "Batería",
                "%",
                status,
                errorCode),
            TelemetryReading.Unavailable(
                "power.ac",
                "Alimentación",
                "bool",
                status,
                errorCode),
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
