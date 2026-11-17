using System.Runtime.InteropServices;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Resuming a game from Big Picture is Steam raising the game's window (steamButton.ts raiseRunningGame). After Big
/// Picture came back over the game by window order (<see cref="GameBarFocusReturner.RaiseBigPictureAsync"/>), Windows
/// refuses that too and Steam's logo stays in front: the host signals every raise through a DevTools binding, and only
/// after such a return does this bring the game's window above Big Picture the same way. A game that was topmost
/// keeps it.
/// </summary>
public sealed class GameWindowRaiser
{
    private const string Binding = "pdcHostRaiseGame";
    private static readonly TimeSpan Reconnect = TimeSpan.FromSeconds(2);
    // Steam's own raise goes first; this one only matters where Windows refused it.
    private static readonly TimeSpan AfterSteam = TimeSpan.FromMilliseconds(300);

    private readonly ISteamDevTools devTools;
    private readonly Func<IReadOnlyDictionary<int, ProcessEntry>> processes;
    private readonly GameBarFocusReturner focus;
    private readonly Func<bool> gameRunning;
    private readonly SemaphoreSlim raise = new(0);
    private ICdpEventSession? session;

    public GameWindowRaiser(
        ISteamDevTools devTools,
        Func<IReadOnlyDictionary<int, ProcessEntry>> processes,
        GameBarFocusReturner focus,
        Func<bool> gameRunning)
    {
        this.devTools = devTools;
        this.processes = processes;
        this.focus = focus;
        this.gameRunning = gameRunning;
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
                    if (!gameRunning())
                    {
                        focus.Foreground.GameEnded();
                        focus.ReleaseBigPicture();
                    }

                    continue;
                }

                await Task.Delay(AfterSteam, cancellationToken).ConfigureAwait(false);
                while (raise.Wait(0))
                {
                    // One resume can signal more than once.
                }

                var needed = focus.Foreground.GameResumed();
                focus.ReleaseBigPicture();
                if (needed)
                {
                    CompanionLog.Write("themes.game_raise", RaiseGameWindow());
                }
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
        var game = WindowOrder.FindTopWindow(
            handle =>
            {
                GetWindowThreadProcessId(handle, out var processId);
                return SteamGameProcesses.IsGame(running, (int)processId);
            },
            minimized: true);
        if (game == IntPtr.Zero)
        {
            return "no_window";
        }

        var topmost = WindowOrder.IsTopmost(game);
        var raised = WindowOrder.Raise(game, stayTopmost: topmost) && WindowOrder.IsOnTop(game, GameBarFocusReturner.IsAppWindow);
        GameBarFocusReturner.AskForeground(game);
        return raised ? (topmost ? "on_top topmost" : "on_top") : "below";
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

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
}
