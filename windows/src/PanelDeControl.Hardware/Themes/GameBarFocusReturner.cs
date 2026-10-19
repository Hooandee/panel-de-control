using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Gives the foreground back to Steam Big Picture after Game Bar closes over it. First Steam is
/// asked to raise itself through its client API; if Windows' foreground lock refuses that, the
/// remembered Big Picture window is raised directly.
/// </summary>
public sealed class GameBarFocusReturner
{
    private static readonly TimeSpan Poll = TimeSpan.FromMilliseconds(250);
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
                continue;
            }

            lastHandle = handle;
            var kind = Classify(handle);
            if (lastKind == ForegroundKind.GameBar && kind != ForegroundKind.GameBar)
            {
                CompanionLog.Write("themes.focus_gamebar_closed", kind.ToString());
            }

            lastKind = kind;
            var restore = tracker.Observe(new ForegroundWindow(handle, kind));
            if (restore != IntPtr.Zero)
            {
                await RestoreAsync(restore, cancellationToken).ConfigureAwait(false);
            }
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

        var raised = IsWindow(steamWindow) && SetForegroundWindow(steamWindow);
        await Task.Delay(200, cancellationToken).ConfigureAwait(false);
        CompanionLog.Write(
            "themes.focus_return",
            GetForegroundWindow() == steamWindow ? "set_foreground_window" : $"failed steam_api={raisedBySteam} set_foreground={raised}");
    }

    private static ForegroundKind Classify(IntPtr handle)
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
                : SteamProcesses.Contains(process.ProcessName) ? ForegroundKind.Steam
                : process.ProcessName.Equals("explorer", StringComparison.OrdinalIgnoreCase) ? ForegroundKind.Shell
                : ForegroundKind.Other;
        }
        catch (ArgumentException)
        {
            return ForegroundKind.Other;
        }
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

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
