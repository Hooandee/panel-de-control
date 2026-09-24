using System.Runtime.InteropServices;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public enum DisplayModeChange
{
    Applied,
    Rejected,
    Failed,
}

public interface IDisplayModeProvider
{
    int? CurrentRefreshRate();

    IReadOnlyList<int> SupportedRefreshRates();

    DisplayModeChange SetRefreshRate(int hertz);
}

public interface IRefreshRateController
{
    RefreshRateResponse Get();

    RefreshRateResponse Set(int hertz);
}

public sealed class RefreshRateController : IRefreshRateController
{
    private readonly IDisplayModeProvider provider;

    public RefreshRateController(IDisplayModeProvider provider)
    {
        this.provider = provider;
    }

    public RefreshRateResponse Get()
    {
        var supported = Plausible(provider.SupportedRefreshRates());
        return provider.CurrentRefreshRate() is int current && RefreshRateRequest.IsPlausible(current)
            ? RefreshRateResponse.Available(current, supported)
            : RefreshRateResponse.Unavailable("display_mode_unreadable");
    }

    public RefreshRateResponse Set(int hertz)
    {
        var supported = Plausible(provider.SupportedRefreshRates());
        var before = provider.CurrentRefreshRate();
        if (!supported.Contains(hertz))
        {
            return RefreshRateResponse.Rejected("refresh_rate_not_supported", supported, Readable(before));
        }

        var change = provider.SetRefreshRate(hertz);
        var observed = Readable(provider.CurrentRefreshRate());
        if (change == DisplayModeChange.Rejected)
        {
            return RefreshRateResponse.Rejected("display_mode_rejected", supported, observed);
        }

        return observed == hertz
            ? RefreshRateResponse.Applied(hertz, hertz, supported)
            : RefreshRateResponse.Unverifiable(
                hertz,
                observed,
                supported,
                change == DisplayModeChange.Failed ? "display_mode_failed" : "refresh_rate_mismatch");
    }

    private static int[] Plausible(IEnumerable<int> rates) =>
        rates.Where(RefreshRateRequest.IsPlausible).Distinct().OrderBy(rate => rate).ToArray();

    private static int? Readable(int? hertz) =>
        hertz is int value && RefreshRateRequest.IsPlausible(value) ? value : null;
}

public sealed class PrimaryDisplayModeProvider : IDisplayModeProvider
{
    private const int EnumCurrentSettings = -1;
    private const int DisplayChangeSuccessful = 0;
    private const int DisplayChangeRestart = 1;
    private const int DisplayChangeBadMode = -2;
    private const uint UpdateRegistry = 0x00000001;
    private const uint FieldDisplayFrequency = 0x00400000;

    public int? CurrentRefreshRate()
    {
        var mode = NewMode();
        return EnumDisplaySettings(null, EnumCurrentSettings, ref mode) ? (int)mode.dmDisplayFrequency : null;
    }

    public IReadOnlyList<int> SupportedRefreshRates()
    {
        var current = NewMode();
        if (!EnumDisplaySettings(null, EnumCurrentSettings, ref current))
        {
            return Array.Empty<int>();
        }

        var rates = new SortedSet<int>();
        var candidate = NewMode();
        for (var index = 0; EnumDisplaySettings(null, index, ref candidate); index++)
        {
            if (candidate.dmPelsWidth == current.dmPelsWidth &&
                candidate.dmPelsHeight == current.dmPelsHeight &&
                candidate.dmBitsPerPel == current.dmBitsPerPel)
            {
                rates.Add((int)candidate.dmDisplayFrequency);
            }

            candidate = NewMode();
        }

        return rates.ToArray();
    }

    public DisplayModeChange SetRefreshRate(int hertz)
    {
        var mode = NewMode();
        if (!EnumDisplaySettings(null, EnumCurrentSettings, ref mode))
        {
            return DisplayModeChange.Failed;
        }

        mode.dmDisplayFrequency = (uint)hertz;
        mode.dmFields = FieldDisplayFrequency;
        var result = ChangeDisplaySettingsEx(null, ref mode, IntPtr.Zero, UpdateRegistry, IntPtr.Zero);
        return result switch
        {
            DisplayChangeSuccessful or DisplayChangeRestart => DisplayModeChange.Applied,
            DisplayChangeBadMode => DisplayModeChange.Rejected,
            _ => DisplayModeChange.Failed,
        };
    }

    private static DisplayMode NewMode() => new() { dmSize = (ushort)Marshal.SizeOf<DisplayMode>() };

    // DEVMODEW display layout; the printer union members are folded into position fields.
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct DisplayMode
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public ushort dmSpecVersion;
        public ushort dmDriverVersion;
        public ushort dmSize;
        public ushort dmDriverExtra;
        public uint dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public uint dmDisplayOrientation;
        public uint dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public ushort dmLogPixels;
        public uint dmBitsPerPel;
        public uint dmPelsWidth;
        public uint dmPelsHeight;
        public uint dmDisplayFlags;
        public uint dmDisplayFrequency;
        public uint dmICMMethod;
        public uint dmICMIntent;
        public uint dmMediaType;
        public uint dmDitherType;
        public uint dmReserved1;
        public uint dmReserved2;
        public uint dmPanningWidth;
        public uint dmPanningHeight;
    }

    [DllImport("user32.dll", EntryPoint = "EnumDisplaySettingsW", CharSet = CharSet.Unicode, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumDisplaySettings(string? deviceName, int modeNumber, ref DisplayMode mode);

    [DllImport("user32.dll", EntryPoint = "ChangeDisplaySettingsExW", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int ChangeDisplaySettingsEx(string? deviceName, ref DisplayMode mode, IntPtr window, uint flags, IntPtr parameter);
}
