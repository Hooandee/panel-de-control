using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Gives the foreground back to Steam Big Picture after Game Bar closes over it. First Steam is
/// asked to raise itself through its client API; if Windows' foreground lock refuses that, the
/// remembered Big Picture window is raised directly. Big Picture can also stay the foreground window
/// while none of Steam's documents has keyboard focus (after Game Bar, a redeploy or waking up): the
/// controller and the theme do nothing until the screen is touched. The focus is then bounced through
/// the shell. Quick access or a menu open is not that: their own document has the focus.
/// </summary>
public sealed class GameBarFocusReturner
{
    private static readonly TimeSpan Poll = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan PageFocusCheck = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan PageUnfocusedGrace = TimeSpan.FromMilliseconds(1500);
    private static readonly TimeSpan BounceRetry = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan BounceRest = TimeSpan.FromSeconds(10);
    private const int BouncesInARow = 3;
    private static readonly HashSet<string> GameBarProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "GameBar", "GameBarFTServer", "XboxGameBarWidgets", "PanelDeControl.GameBar",
    };
    private static readonly HashSet<string> SteamProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "steam", "steamwebhelper",
    };
    private static readonly HashSet<string> ShellClasses = new(StringComparer.Ordinal)
    {
        "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    };

    private readonly SteamThemeEngine engine;
    private readonly GameBarFocusTracker tracker = new();
    private IntPtr lastHandle;
    private ForegroundKind lastKind = ForegroundKind.Other;
    private ICdpSession? sharedContext;
    private DateTimeOffset nextPageCheck = DateTimeOffset.MinValue;
    private DateTimeOffset? pageUnfocusedSince;
    private DateTimeOffset nextBounce = DateTimeOffset.MinValue;
    private int failedBounces;

    public GameBarFocusReturner(SteamThemeEngine engine)
    {
        this.engine = engine;
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await Task.Delay(Poll, cancellationToken).ConfigureAwait(false);
            var handle = GetForegroundWindow();
            if (handle == lastHandle)
            {
                if (lastKind == ForegroundKind.Steam)
                {
                    await KeepPageFocusAsync(handle, cancellationToken).ConfigureAwait(false);
                }

                continue;
            }

            pageUnfocusedSince = null;

            lastHandle = handle;
            var kind = Classify(handle);
            if (lastKind != kind && (lastKind == ForegroundKind.Steam || kind == ForegroundKind.Steam || lastKind == ForegroundKind.GameBar))
            {
                CompanionLog.Write("themes.focus_foreground", $"{lastKind}->{kind}");
            }

            lastKind = kind;
            var restore = tracker.Observe(new ForegroundWindow(handle, kind));
            if (restore != IntPtr.Zero)
            {
                await RestoreAsync(restore, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async Task KeepPageFocusAsync(IntPtr steamWindow, CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow;
        if (now < nextPageCheck)
        {
            return;
        }

        nextPageCheck = now + PageFocusCheck;
        var focused = await SteamUiHasFocusAsync(cancellationToken).ConfigureAwait(false);
        if (focused != false)
        {
            pageUnfocusedSince = null;
            failedBounces = 0;
            return;
        }

        pageUnfocusedSince ??= now;
        if (now - pageUnfocusedSince < PageUnfocusedGrace || now < nextBounce)
        {
            return;
        }

        keybd_event(VkMenu, 0, 0, UIntPtr.Zero);
        keybd_event(VkMenu, 0, KeyEventKeyUp, UIntPtr.Zero);
        SetForegroundWindow(GetShellWindow());
        await Task.Delay(60, cancellationToken).ConfigureAwait(false);
        keybd_event(VkMenu, 0, 0, UIntPtr.Zero);
        keybd_event(VkMenu, 0, KeyEventKeyUp, UIntPtr.Zero);
        SetForegroundWindow(steamWindow);
        await Task.Delay(300, cancellationToken).ConfigureAwait(false);
        var restored = await SteamUiHasFocusAsync(cancellationToken).ConfigureAwait(false) == true;
        failedBounces = restored ? 0 : failedBounces + 1;
        nextBounce = DateTimeOffset.UtcNow + (failedBounces is > 0 and < BouncesInARow ? BounceRetry : BounceRest);
        if (failedBounces >= BouncesInARow)
        {
            failedBounces = 0;
        }

        CompanionLog.Write("themes.focus_bounce", restored ? "steam_ui_focused" : "steam_ui_still_unfocused");
    }

    // Every Steam document that hosts a navigation tree (Big Picture, quick access, menus, keyboard).
    private const string SteamUiFocusExpression = """
        (() => {
          const docs = new Set();
          const page = SteamUIStore?.WindowStore?.GamepadUIMainWindowInstance?.BrowserWindow?.document;
          if (page) docs.add(page);
          for (const context of globalThis.FocusNavController?.m_rgAllContexts ?? []) {
            for (const tree of context?.m_rgGamepadNavigationTrees ?? []) {
              const doc = tree?.Root?.Element?.ownerDocument ?? tree?.m_Root?.Element?.ownerDocument;
              if (doc) docs.add(doc);
            }
          }
          if (!docs.size) return null;
          for (const doc of docs) {
            try { if (doc.hasFocus()) return true; } catch { }
          }
          return false;
        })()
        """;

    /// <summary>Whether any of Steam's UI documents has keyboard focus, or null when Steam cannot be asked.</summary>
    private async Task<bool?> SteamUiHasFocusAsync(CancellationToken cancellationToken)
    {
        try
        {
            if (sharedContext is null || !sharedContext.IsOpen)
            {
                if (sharedContext is not null)
                {
                    await sharedContext.DisposeAsync().ConfigureAwait(false);
                }

                sharedContext = await engine.ConnectSharedContextAsync(cancellationToken).ConfigureAwait(false);
            }

            if (sharedContext is null)
            {
                return null;
            }

            var focused = await sharedContext.EvaluateAsync(SteamUiFocusExpression, cancellationToken).ConfigureAwait(false);
            return focused.ValueKind switch
            {
                System.Text.Json.JsonValueKind.True => true,
                System.Text.Json.JsonValueKind.False => false,
                _ => null,
            };
        }
        catch (Exception exception) when (exception is CdpException or System.Net.WebSockets.WebSocketException
            or System.Net.Http.HttpRequestException or InvalidOperationException or OperationCanceledException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            sharedContext = null;
            return null;
        }
    }

    private async Task RestoreAsync(IntPtr steamWindow, CancellationToken cancellationToken)
    {
        var raisedBySteam = await engine.BringBigPictureToFrontAsync(cancellationToken).ConfigureAwait(false);
        await Task.Delay(400, cancellationToken).ConfigureAwait(false);
        if (GetForegroundWindow() == steamWindow)
        {
            CompanionLog.Write("themes.focus_return", "steam_bring_to_front");
            return;
        }

        // Windows refuses SetForegroundWindow to a process that did not get the last input event (foreground lock);
        // a synthetic Alt press counts as that input (RC73XA, 2026-10-21).
        for (var attempt = 1; attempt <= RestoreAttempts; attempt++)
        {
            if (!IsWindow(steamWindow))
            {
                break;
            }

            keybd_event(VkMenu, 0, 0, UIntPtr.Zero);
            keybd_event(VkMenu, 0, KeyEventKeyUp, UIntPtr.Zero);
            SetForegroundWindow(steamWindow);
            await Task.Delay(200, cancellationToken).ConfigureAwait(false);
            if (GetForegroundWindow() == steamWindow)
            {
                CompanionLog.Write("themes.focus_return", $"set_foreground_window attempt={attempt}");
                return;
            }
        }

        CompanionLog.Write("themes.focus_return", $"failed steam_api={raisedBySteam} attempts={RestoreAttempts}");
    }

    internal static ForegroundKind Classify(IntPtr handle)
    {
        if (handle == IntPtr.Zero)
        {
            return ForegroundKind.Shell;
        }

        var className = new StringBuilder(64);
        if (GetClassName(handle, className, className.Capacity) > 0 && ShellClasses.Contains(className.ToString()))
        {
            return ForegroundKind.Shell;
        }

        GetWindowThreadProcessId(handle, out var processId);
        try
        {
            using var process = Process.GetProcessById((int)processId);
            return GameBarProcesses.Contains(process.ProcessName) ? ForegroundKind.GameBar
                : SteamProcesses.Contains(process.ProcessName) ? (CoversItsMonitor(handle) ? ForegroundKind.Steam : ForegroundKind.Other)
                : process.ProcessName.Equals("explorer", StringComparison.OrdinalIgnoreCase) ? ForegroundKind.Shell
                : ForegroundKind.Other;
        }
        catch (ArgumentException)
        {
            return ForegroundKind.Other;
        }
    }

    // Only a full screen Steam window (Big Picture) is restored; the desktop client is left alone.
    private static bool CoversItsMonitor(IntPtr handle)
    {
        var monitor = MonitorFromWindow(handle, MonitorDefaultToNearest);
        var info = new MonitorInfo { cbSize = Marshal.SizeOf<MonitorInfo>() };
        return GetWindowRect(handle, out var window)
            && GetMonitorInfo(monitor, ref info)
            && window.Left <= info.rcMonitor.Left && window.Top <= info.rcMonitor.Top
            && window.Right >= info.rcMonitor.Right && window.Bottom >= info.rcMonitor.Bottom;
    }

    private const uint MonitorDefaultToNearest = 2;
    private const int RestoreAttempts = 3;
    private const byte VkMenu = 0x12;
    private const uint KeyEventKeyUp = 0x0002;

    [DllImport("user32.dll")]
    private static extern IntPtr GetShellWindow();

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte virtualKey, byte scanCode, uint flags, UIntPtr extraInfo);


    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left, Top, Right, Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MonitorInfo
    {
        public int cbSize;
        public Rect rcMonitor, rcWork;
        public uint dwFlags;
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromWindow(IntPtr hWnd, uint flags);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

    [DllImport("user32.dll")]
    internal static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindow(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder className, int maxCount);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
