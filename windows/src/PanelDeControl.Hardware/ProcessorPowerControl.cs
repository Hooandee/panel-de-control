using System.Runtime.InteropServices;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public enum PowerSettingsWrite
{
    Applied,
    AccessDenied,
    Failed,
}

public readonly struct ProcessorPowerState
{
    public ProcessorPowerState(uint boostMode, uint maximumStatePercent)
    {
        BoostMode = boostMode;
        MaximumStatePercent = maximumStatePercent;
    }

    public uint BoostMode { get; }

    public uint MaximumStatePercent { get; }
}

public interface IProcessorPowerSettings
{
    ProcessorPowerState? ReadActive(out bool accessDenied);

    PowerSettingsWrite Write(uint? boostMode, uint? maximumStatePercent);
}

public interface ICpuController
{
    CpuControlResponse Get();

    CpuControlResponse SetBoost(bool enabled);

    CpuControlResponse SetMaximumState(int percent);
}

public sealed class CpuController : ICpuController
{
    private const uint BoostDisabled = 0;
    private const uint BoostAggressive = 2;

    private readonly object gate = new();
    private readonly IProcessorPowerSettings settings;
    private uint? lastEnabledBoostMode;

    public CpuController(IProcessorPowerSettings settings)
    {
        this.settings = settings;
    }

    public CpuControlResponse Get()
    {
        lock (gate)
        {
            return Read(out var state) ?? Available(state!.Value);
        }
    }

    public CpuControlResponse SetBoost(bool enabled)
    {
        lock (gate)
        {
            var failure = Read(out var before);
            if (failure is not null)
            {
                return failure;
            }

            if (before!.Value.BoostMode != BoostDisabled)
            {
                lastEnabledBoostMode = before.Value.BoostMode;
            }

            var mode = enabled ? lastEnabledBoostMode ?? BoostAggressive : BoostDisabled;
            return Verify(settings.Write(mode, null), state => (state.BoostMode != BoostDisabled) == enabled);
        }
    }

    public CpuControlResponse SetMaximumState(int percent)
    {
        if (!CpuControlRequest.IsState(percent))
        {
            return CpuControlResponse.Rejected("cpu_state_out_of_range");
        }

        lock (gate)
        {
            return Verify(settings.Write(null, (uint)percent), state => state.MaximumStatePercent == percent);
        }
    }

    private CpuControlResponse Verify(PowerSettingsWrite write, Func<ProcessorPowerState, bool> matches)
    {
        if (write == PowerSettingsWrite.AccessDenied)
        {
            return CpuControlResponse.PermissionRequired("power_settings_permission_required");
        }

        var failure = Read(out var after);
        if (failure is not null)
        {
            return CpuControlResponse.Unverifiable(null, null, "power_settings_unreadable");
        }

        var state = after!.Value;
        if (write == PowerSettingsWrite.Applied && matches(state))
        {
            return CpuControlResponse.Applied(state.BoostMode != BoostDisabled, (int)state.MaximumStatePercent);
        }

        return CpuControlResponse.Unverifiable(
            state.BoostMode != BoostDisabled,
            (int)state.MaximumStatePercent,
            write == PowerSettingsWrite.Failed ? "power_settings_write_failed" : "power_settings_mismatch");
    }

    private CpuControlResponse? Read(out ProcessorPowerState? state)
    {
        try
        {
            state = settings.ReadActive(out var accessDenied);
            if (accessDenied)
            {
                return CpuControlResponse.PermissionRequired("power_settings_permission_required");
            }

            if (state is null)
            {
                return CpuControlResponse.Unavailable("power_settings_unavailable");
            }

            return CpuControlRequest.IsState((int)Math.Min(state.Value.MaximumStatePercent, int.MaxValue))
                ? null
                : CpuControlResponse.Unavailable("power_settings_implausible");
        }
        catch
        {
            state = null;
            return CpuControlResponse.Fault("power_settings_failed");
        }
    }

    private static CpuControlResponse Available(ProcessorPowerState state) =>
        CpuControlResponse.Available(state.BoostMode != BoostDisabled, (int)state.MaximumStatePercent);

}

public sealed class ActiveSchemeProcessorPowerSettings : IProcessorPowerSettings
{
    private const uint ErrorSuccess = 0;
    private const uint ErrorAccessDenied = 5;

    private static readonly Guid ProcessorSubgroup = new("54533251-82be-4824-96c1-47b60b740d00");
    private static readonly Guid BoostModeSetting = new("be337238-0d82-4146-a960-4f3749d470c7");
    private static readonly Guid MaximumStateSetting = new("bc5038f7-23e0-4960-96da-33abaf5935ec");

    public ProcessorPowerState? ReadActive(out bool accessDenied)
    {
        accessDenied = false;
        if (!OperatingSystem.IsWindows() || !TryGetActiveScheme(out var scheme))
        {
            return null;
        }

        var onExternalPower = GetSystemPowerStatus(out var status) && status.AcLineStatus == 1;
        var boost = ReadIndex(scheme, BoostModeSetting, onExternalPower, out var boostResult);
        var maximum = ReadIndex(scheme, MaximumStateSetting, onExternalPower, out var maximumResult);
        accessDenied = boostResult == ErrorAccessDenied || maximumResult == ErrorAccessDenied;
        return boost.HasValue && maximum.HasValue
            ? new ProcessorPowerState(boost.Value, maximum.Value)
            : null;
    }

    public PowerSettingsWrite Write(uint? boostMode, uint? maximumStatePercent)
    {
        if (!OperatingSystem.IsWindows() || !TryGetActiveScheme(out var scheme))
        {
            return PowerSettingsWrite.Failed;
        }

        var results = new List<uint>();
        if (boostMode is uint mode)
        {
            results.Add(WriteBoth(scheme, BoostModeSetting, mode));
        }

        if (maximumStatePercent is uint percent)
        {
            results.Add(WriteBoth(scheme, MaximumStateSetting, percent));
        }

        if (results.Contains(ErrorAccessDenied))
        {
            return PowerSettingsWrite.AccessDenied;
        }

        var applied = results.All(result => result == ErrorSuccess) && PowerSetActiveScheme(IntPtr.Zero, ref scheme) == ErrorSuccess;
        return applied ? PowerSettingsWrite.Applied : PowerSettingsWrite.Failed;
    }

    private static uint WriteBoth(Guid scheme, Guid setting, uint value)
    {
        var subgroup = ProcessorSubgroup;
        var ac = PowerWriteACValueIndex(IntPtr.Zero, ref scheme, ref subgroup, ref setting, value);
        var dc = PowerWriteDCValueIndex(IntPtr.Zero, ref scheme, ref subgroup, ref setting, value);
        return ac != ErrorSuccess ? ac : dc;
    }

    private static uint? ReadIndex(Guid scheme, Guid setting, bool onExternalPower, out uint result)
    {
        var subgroup = ProcessorSubgroup;
        uint value;
        result = onExternalPower
            ? PowerReadACValueIndex(IntPtr.Zero, ref scheme, ref subgroup, ref setting, out value)
            : PowerReadDCValueIndex(IntPtr.Zero, ref scheme, ref subgroup, ref setting, out value);
        return result == ErrorSuccess ? value : null;
    }

    private static bool TryGetActiveScheme(out Guid scheme)
    {
        scheme = Guid.Empty;
        if (PowerGetActiveScheme(IntPtr.Zero, out var pointer) != ErrorSuccess || pointer == IntPtr.Zero)
        {
            return false;
        }

        try
        {
            scheme = Marshal.PtrToStructure<Guid>(pointer);
            return true;
        }
        finally
        {
            LocalFree(pointer);
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemPowerStatus
    {
        public byte AcLineStatus;
        public byte BatteryFlag;
        public byte BatteryLifePercent;
        public byte SystemStatusFlag;
        public uint BatteryLifeTime;
        public uint BatteryFullLifeTime;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSystemPowerStatus(out SystemPowerStatus status);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    [DllImport("powrprof.dll")]
    private static extern uint PowerGetActiveScheme(IntPtr userRootPowerKey, out IntPtr activePolicyGuid);

    [DllImport("powrprof.dll")]
    private static extern uint PowerSetActiveScheme(IntPtr userRootPowerKey, ref Guid schemeGuid);

    [DllImport("powrprof.dll")]
    private static extern uint PowerReadACValueIndex(IntPtr rootPowerKey, ref Guid schemeGuid, ref Guid subgroupGuid, ref Guid settingGuid, out uint value);

    [DllImport("powrprof.dll")]
    private static extern uint PowerReadDCValueIndex(IntPtr rootPowerKey, ref Guid schemeGuid, ref Guid subgroupGuid, ref Guid settingGuid, out uint value);

    [DllImport("powrprof.dll")]
    private static extern uint PowerWriteACValueIndex(IntPtr rootPowerKey, ref Guid schemeGuid, ref Guid subgroupGuid, ref Guid settingGuid, uint value);

    [DllImport("powrprof.dll")]
    private static extern uint PowerWriteDCValueIndex(IntPtr rootPowerKey, ref Guid schemeGuid, ref Guid subgroupGuid, ref Guid settingGuid, uint value);
}
