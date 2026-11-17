using System.Runtime.InteropServices;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Resuming a game from Big Picture is Steam raising the game's window (steamButton.ts raiseRunningGame). After Big
/// Picture came back over the game by window order, Windows refuses that too and Steam's logo stays in front: the
/// host signals the raise through a DevTools binding and this brings the game's window above Big Picture the same way.
/// </summary>
public sealed class GameWindowRaiser
{
    private const string Binding = "pdcHostRaiseGame";
    private static readonly TimeSpan Reconnect = TimeSpan.FromSeconds(2);
    // Steam's own raise goes first; this one only matters where Windows refused it.
    private static readonly TimeSpan AfterSteam = TimeSpan.FromMilliseconds(300);

    private readonly ISteamDevTools devTools;
    private readonly Func<IReadOnlyDictionary<int, ProcessEntry>> processes;
    private readonly SemaphoreSlim raise = new(0);
    private ICdpEventSession? session;

    public GameWindowRaiser(ISteamDevTools devTools, Func<IReadOnlyDictionary<int, ProcessEntry>> processes)
    {
        this.devTools = devTools;
        this.processes = processes;
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await KeepSessionAsync(cancellationToken).ConfigureAwait(false);
                if (!await raise.WaitAsync(Reconnect, cancellationToken).ConfigureAwait(false))
                {
                    continue;
                }

                await Task.Delay(AfterSteam, cancellationToken).ConfigureAwait(false);
                CompanionLog.Write("themes.game_raise", RaiseGameWindow());
            }
        }
        finally
        {
            await CloseAsync().ConfigureAwait(false);
        }
    }

    private string RaiseGameWindow()
    {
        var running = processes();
        var game = WindowOrder.FindTopWindow(handle =>
        {
            GetWindowThreadProcessId(handle, out var processId);
            return SteamGameProcesses.IsGame(running, (int)processId) && HasArea(handle);
        });
        if (game == IntPtr.Zero)
        {
            return "no_window";
        }

        var ordered = WindowOrder.BringAbove(game);
        GameBarFocusReturner.AskForeground(game);
        return ordered ? "window_order" : "window_order_failed";
    }

    private async Task KeepSessionAsync(CancellationToken cancellationToken)
    {
        if (session is { IsOpen: true })
        {
            return;
        }

        await CloseAsync().ConfigureAwait(false);
        try
        {
            var targets = await devTools.ListTargetsAsync(cancellationToken).ConfigureAwait(false);
            var shared = targets?.FirstOrDefault(target => target.Title == SteamThemeEngine.SharedContextTitle);
            if (shared is null || await devTools.ConnectAsync(shared, cancellationToken).ConfigureAwait(false) is not ICdpEventSession connected)
            {
                return;
            }

            connected.EventReceived += OnEvent;
            session = connected;
            await connected.SendAsync("Runtime.addBinding", new { name = Binding }, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is CdpException or System.Net.WebSockets.WebSocketException or HttpRequestException
            or InvalidOperationException or OperationCanceledException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await CloseAsync().ConfigureAwait(false);
        }
    }

    private void OnEvent(string method, JsonElement parameters)
    {
        if (method == "Runtime.bindingCalled"
            && parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("name", out var name)
            && name.ValueEquals(Binding))
        {
            raise.Release();
        }
    }

    private async Task CloseAsync()
    {
        var closing = session;
        session = null;
        if (closing is not null)
        {
            closing.EventReceived -= OnEvent;
            await closing.DisposeAsync().ConfigureAwait(false);
        }
    }

    private static bool HasArea(IntPtr handle) =>
        GetWindowRect(handle, out var rect) && rect.Right - rect.Left > 1 && rect.Bottom - rect.Top > 1;

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left, Top, Right, Bottom;
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr handle, out Rect rect);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
}
