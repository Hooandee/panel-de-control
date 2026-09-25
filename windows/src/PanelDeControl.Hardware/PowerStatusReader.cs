using System.Runtime.InteropServices;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public readonly record struct NativePowerStatus(
    byte AcLineStatus,
    byte BatteryLifePercent);

public readonly record struct NativeBatteryState(
    bool BatteryPresent,
    bool Charging,
    bool Discharging,
    int RateMilliwatts,
    uint EstimatedSeconds);

public readonly record struct NativePowerModes(Guid? Actual, Guid? Effective);

public sealed class PowerStatusReader : IPowerStatusReader
{
    private readonly IBatteryHealthSource batteryHealth;

    public PowerStatusReader(IBatteryHealthSource? batteryHealth = null)
    {
        this.batteryHealth = batteryHealth ?? new WmiBatteryHealthSource();
    }

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

        return Map(new NativePowerStatus(status.AcLineStatus, status.BatteryLifePercent))
            .Concat(MapEnergy(ReadBatteryState()))
            .Concat(MapModes(ReadPowerModes()))
            .Concat(batteryHealth.Read())
            .ToArray();
    }

    public static IReadOnlyList<TelemetryReading> MapEnergy(NativeBatteryState? state)
    {
        const string source = "win32/SystemBatteryState";
        if (state is not { BatteryPresent: true } battery)
        {
            return new[]
            {
                TelemetryReading.Unavailable("power.draw", "Consumo", "W", ReadingStatus.Unavailable, "battery_state_unavailable"),
                TelemetryReading.Unavailable("battery.time_remaining", "Autonomía", "min", ReadingStatus.Unavailable, "battery_state_unavailable"),
            };
        }

        var draw = !battery.Discharging
            ? TelemetryReading.Unavailable("power.draw", "Consumo", "W", ReadingStatus.Unavailable, "power_draw_on_ac")
            : battery.RateMilliwatts < 0
                ? TelemetryReading.Available("power.draw", "Consumo", Math.Round(-battery.RateMilliwatts / 1000.0, 1), "W", source)
                : TelemetryReading.Unavailable("power.draw", "Consumo", "W", ReadingStatus.Unavailable, "power_draw_pending");
        var remaining = battery.Discharging && battery.EstimatedSeconds is > 0 and < uint.MaxValue
            ? TelemetryReading.Available("battery.time_remaining", "Autonomía", Math.Round(battery.EstimatedSeconds / 60.0), "min", source)
            : TelemetryReading.Unavailable("battery.time_remaining", "Autonomía", "min", ReadingStatus.Unavailable, "time_remaining_unknown");
        return new[] { draw, remaining };
    }

    public static IReadOnlyList<TelemetryReading> MapModes(NativePowerModes modes)
    {
        return new[]
        {
            ModeReading("power.mode", modes.Actual),
            ModeReading("power.mode_effective", modes.Effective),
        };
    }

    private static TelemetryReading ModeReading(string id, Guid? overlay)
    {
        if (overlay is not Guid value)
        {
            return TelemetryReading.Unavailable(id, "Modo de energía", "mode", ReadingStatus.Fault, "power_mode_failed");
        }

        return PowerModes.FromOverlay(value) is PowerMode mode
            ? TelemetryReading.Available(id, "Modo de energía", (int)mode, "mode", "win32/PowerOverlayScheme")
            : TelemetryReading.Unavailable(id, "Modo de energía", "mode", ReadingStatus.Unavailable, "power_mode_unknown");
    }

    private static NativeBatteryState? ReadBatteryState()
    {
        try
        {
            var size = (uint)Marshal.SizeOf<SystemBatteryState>();
            if (CallNtPowerInformation(SystemBatteryStateLevel, IntPtr.Zero, 0, out var state, size) != 0)
            {
                return null;
            }

            return new NativeBatteryState(state.BatteryPresent, state.Charging, state.Discharging, state.Rate, state.EstimatedTime);
        }
        catch (DllNotFoundException)
        {
            return null;
        }
        catch (EntryPointNotFoundException)
        {
            return null;
        }
    }

    private static NativePowerModes ReadPowerModes()
    {
        try
        {
            Guid? actual = PowerGetActualOverlayScheme(out var actualGuid) == 0 ? actualGuid : null;
            Guid? effective = PowerGetEffectiveOverlayScheme(out var effectiveGuid) == 0 ? effectiveGuid : null;
            return new NativePowerModes(actual, effective);
        }
        catch (EntryPointNotFoundException)
        {
            return new NativePowerModes(null, null);
        }
        catch (DllNotFoundException)
        {
            return new NativePowerModes(null, null);
        }
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

    private const int SystemBatteryStateLevel = 5;

    [DllImport("powrprof.dll")]
    private static extern uint CallNtPowerInformation(
        int informationLevel,
        IntPtr inputBuffer,
        uint inputBufferLength,
        out SystemBatteryState outputBuffer,
        uint outputBufferLength);

    [DllImport("powrprof.dll")]
    private static extern uint PowerGetActualOverlayScheme(out Guid overlayScheme);

    [DllImport("powrprof.dll")]
    private static extern uint PowerGetEffectiveOverlayScheme(out Guid overlayScheme);

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemBatteryState
    {
        [MarshalAs(UnmanagedType.U1)]
        public bool AcOnLine;
        [MarshalAs(UnmanagedType.U1)]
        public bool BatteryPresent;
        [MarshalAs(UnmanagedType.U1)]
        public bool Charging;
        [MarshalAs(UnmanagedType.U1)]
        public bool Discharging;
        public byte Spare1;
        public byte Spare2;
        public byte Spare3;
        public byte Spare4;
        public uint MaxCapacity;
        public uint RemainingCapacity;
        public int Rate;
        public uint EstimatedTime;
        public uint DefaultAlert1;
        public uint DefaultAlert2;
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
