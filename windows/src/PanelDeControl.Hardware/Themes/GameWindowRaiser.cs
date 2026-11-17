using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Resuming a game from Big Picture is Steam raising the game's window (steamButton.ts raiseRunningGame). After Big
/// Picture came back over the game by window order (<see cref="GameBarFocusReturner.RaiseBigPictureAsync"/>), Windows
/// refuses that too and Steam's logo stays in front: the host signals every raise through a DevTools binding, and only
/// after such a return does this bring the game back (<see cref="GameBarFocusReturner.GameResumedAsync"/>).
/// </summary>
public sealed class GameWindowRaiser
{
    private const string Binding = "pdcHostRaiseGame";
    private static readonly TimeSpan Reconnect = TimeSpan.FromSeconds(2);
    // Steam's own raise goes first; this one only matters where Windows refused it.
    private static readonly TimeSpan AfterSteam = TimeSpan.FromMilliseconds(300);
    private static readonly TimeSpan GameStarting = TimeSpan.FromSeconds(5);

    private readonly ISteamDevTools devTools;
    private readonly Func<IReadOnlyDictionary<int, ProcessEntry>> processes;
    private readonly GameBarFocusReturner focus;
    private readonly Func<bool?> gameRunning;
    private readonly GamePresence presence = new();
    private readonly SemaphoreSlim raise = new(0);
    private ICdpEventSession? session;

    public GameWindowRaiser(
        ISteamDevTools devTools,
        Func<IReadOnlyDictionary<int, ProcessEntry>> processes,
        GameBarFocusReturner focus,
        Func<bool?> gameRunning)
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
                    switch (presence.Read(gameRunning()))
                    {
                        case GamePresenceChange.Started:
                            // Its window takes the foreground through the shell.
                            focus.HoldStill(GameStarting);
                            break;
                        case GamePresenceChange.Ended:
                            focus.Foreground.GameEnded();
                            focus.ReleaseBigPicture();
                            break;
                    }

                    continue;
                }

                await Task.Delay(AfterSteam, cancellationToken).ConfigureAwait(false);
                while (raise.Wait(0))
                {
                    // One resume can signal more than once.
                }

                var raised = await focus.GameResumedAsync(FindGameWindow, cancellationToken).ConfigureAwait(false);
                if (raised is not null)
                {
                    CompanionLog.Write("themes.game_raise", raised);
                }
            }
        }
        finally
        {
            await CloseAsync().ConfigureAwait(false);
        }
    }

    // In Xbox mode the shell cloaks a game while another app is in front: it is looked for among cloaked windows too.
    private IntPtr FindGameWindow()
    {
        var running = processes();
        return WindowOrder.FindTopWindow(handle => SteamGameProcesses.IsGame(running, WindowOrder.ProcessOf(handle)), background: true);
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
}
