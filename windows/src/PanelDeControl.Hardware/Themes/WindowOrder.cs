using System.Runtime.InteropServices;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Once Game Bar has closed over a game on the ROG Xbox Ally X, Windows refuses the foreground to Steam and to
/// <c>SetForegroundWindow</c>, both for Big Picture and for the game coming back. Changing the window order needs no
/// foreground rights. A window goes topmost and, unless it has to stay above a topmost window, straight back, which
/// leaves it above every other normal window.
/// </summary>
internal static class WindowOrder
{
    private const uint SwpNoSize = 0x0001;
    private const uint SwpNoMove = 0x0002;
    private const uint SwpNoActivate = 0x0010;
    private const uint SwpShowWindow = 0x0040;
    private const uint KeepPlace = SwpNoSize | SwpNoMove | SwpShowWindow;
    private const int GwlExStyle = -20;
    private const int WsExTopmost = 0x00000008;
    private const int WsExToolWindow = 0x00000080;
    private const uint GwOwner = 4;
    private const int DwmCloaked = 14;
    private const int SwRestore = 9;
    private static readonly IntPtr HwndTopmost = new(-1);
    private static readonly IntPtr HwndNoTopmost = new(-2);

    /// <summary>Brings the window above every normal window; it stays topmost only when told to.</summary>
    public static bool Raise(IntPtr handle, bool stayTopmost)
    {
        if (IsIconic(handle))
        {
            ShowWindow(handle, SwRestore);
        }

        return SetWindowPos(handle, HwndTopmost, 0, 0, 0, 0, KeepPlace)
            && (stayTopmost || SetWindowPos(handle, HwndNoTopmost, 0, 0, 0, 0, KeepPlace));
    }

    public static void Release(IntPtr handle) =>
        SetWindowPos(handle, HwndNoTopmost, 0, 0, 0, 0, SwpNoSize | SwpNoMove | SwpNoActivate);

    public static bool IsTopmost(IntPtr handle) => (GetWindowLong(handle, GwlExStyle) & WsExTopmost) != 0;

    public static bool IsOnTop(IntPtr handle, Func<IntPtr, bool> counts) => FindTopWindow(counts) == handle;

    /// <summary>
    /// The first window the player can see, in window order, that matches: top-level, shown and not cloaked by the
    /// shell, without an owner, not a tool window, and not minimized unless <paramref name="minimized"/>.
    /// </summary>
    public static IntPtr FindTopWindow(Func<IntPtr, bool> matches, bool minimized = false)
    {
        var found = IntPtr.Zero;
        EnumWindows((handle, _) =>
        {
            if (IsWindowVisible(handle)
                && !IsCloaked(handle)
                && GetWindow(handle, GwOwner) == IntPtr.Zero
                && (GetWindowLong(handle, GwlExStyle) & WsExToolWindow) == 0
                && (minimized || !IsIconic(handle))
                && HasArea(handle)
                && matches(handle))
            {
                found = handle;
                return false;
            }

            return true;
        }, IntPtr.Zero);
        return found;
    }

    private static bool IsCloaked(IntPtr handle) =>
        DwmGetWindowAttribute(handle, DwmCloaked, out var cloaked, sizeof(int)) == 0 && cloaked != 0;

    private static bool HasArea(IntPtr handle) =>
        IsIconic(handle) || (GetWindowRect(handle, out var rect) && rect.Right - rect.Left > 1 && rect.Bottom - rect.Top > 1);

    private delegate bool EnumWindowsProc(IntPtr handle, IntPtr parameter);

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left, Top, Right, Bottom;
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(IntPtr handle, IntPtr insertAfter, int x, int y, int width, int height, uint flags);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr handle);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsIconic(IntPtr handle);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(IntPtr handle, int command);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr handle, uint command);

    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr handle, int index);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr handle, out Rect rect);

    [DllImport("dwmapi.dll")]
    private static extern int DwmGetWindowAttribute(IntPtr handle, int attribute, out int value, int size);
}
