using System.Runtime.InteropServices;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Once Game Bar has closed over a game on the ROG Xbox Ally X, Windows refuses the foreground to Steam and to
/// <c>SetForegroundWindow</c>, both for Big Picture and for the game coming back. Changing the window order needs no
/// foreground rights: a window goes topmost and straight back, which leaves it above every other normal window.
/// </summary>
internal static class WindowOrder
{
    private const uint SwpNoSize = 0x0001;
    private const uint SwpNoMove = 0x0002;
    private const uint SwpShowWindow = 0x0040;
    private static readonly IntPtr HwndTopmost = new(-1);
    private static readonly IntPtr HwndNoTopmost = new(-2);

    public static bool BringAbove(IntPtr handle)
    {
        const uint keepPlace = SwpNoSize | SwpNoMove | SwpShowWindow;
        return SetWindowPos(handle, HwndTopmost, 0, 0, 0, 0, keepPlace)
            && SetWindowPos(handle, HwndNoTopmost, 0, 0, 0, 0, keepPlace);
    }

    /// <summary>The first visible top-level window, in window order, that matches.</summary>
    public static IntPtr FindTopWindow(Func<IntPtr, bool> matches)
    {
        var found = IntPtr.Zero;
        EnumWindows((handle, _) =>
        {
            if (IsWindowVisible(handle) && matches(handle))
            {
                found = handle;
                return false;
            }

            return true;
        }, IntPtr.Zero);
        return found;
    }

    private delegate bool EnumWindowsProc(IntPtr handle, IntPtr parameter);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(IntPtr handle, IntPtr insertAfter, int x, int y, int width, int height, uint flags);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr handle);
}
