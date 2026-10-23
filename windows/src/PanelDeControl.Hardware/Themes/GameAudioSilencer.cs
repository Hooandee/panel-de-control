using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Steam on Windows has no per-app audio service, so a theme that silences the running game while Steam is in
/// front asks the theme host (<c>__pdcHostGameAudio</c>), and this mutes the game's sessions in Windows' mixer.
/// A DevTools binding wakes it the moment the host's state changes; the state itself is always read from the host.
/// On Windows the game keeps running behind Big Picture, so the theme's request only silences it while Big Picture
/// itself is in front: right after a launch Steam still shows the game's page with the game already in front.
/// When Steam or the host goes away, every game silenced here gets its sound back.
/// </summary>
public sealed class GameAudioSilencer
{
    private const string Binding = "pdcHostGameAudio";
    private const string StateExpression = "window.__pdcWindowsThemeHost?.status?.().gameSilenced === true";
    private static readonly TimeSpan ActivePoll = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan IdlePoll = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan Rescan = TimeSpan.FromSeconds(1);

    private readonly ISteamDevTools devTools;
    private readonly IGameAudioMixer mixer;
    private readonly GameAudioPolicy policy;
    private readonly SemaphoreSlim wake = new(0);
    private readonly Func<bool> bigPictureInFront;
    private ICdpEventSession? session;

    public GameAudioSilencer(ISteamDevTools devTools, IGameAudioMixer mixer, GameAudioPolicy policy, Func<bool> bigPictureInFront)
    {
        this.devTools = devTools;
        this.mixer = mixer;
        this.policy = policy;
        this.bigPictureInFront = bigPictureInFront;
    }

    public static bool ForegroundIsBigPicture() =>
        GameBarFocusReturner.Classify(GameBarFocusReturner.GetForegroundWindow()) == ForegroundKind.Steam;

    public static string DefaultStatePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "game-audio-silenced.json");

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            bool? applied = null;
            var appliedAt = DateTimeOffset.MinValue;
            while (!cancellationToken.IsCancellationRequested)
            {
                var requested = await ReadStateAsync(cancellationToken).ConfigureAwait(false);
                var silenced = requested && bigPictureInFront();
                var now = DateTimeOffset.UtcNow;
                if ((silenced || policy.HasOwed) && (silenced != applied || now - appliedAt >= Rescan))
                {
                    Apply(silenced);
                    applied = silenced;
                    appliedAt = now;
                }
                else if (!silenced && !policy.HasOwed)
                {
                    applied = false;
                }

                await wake.WaitAsync(requested || policy.HasOwed ? ActivePoll : IdlePoll, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            if (policy.HasOwed)
            {
                Apply(false);
            }

            await CloseAsync().ConfigureAwait(false);
        }
    }

    private async Task<bool> ReadStateAsync(CancellationToken cancellationToken)
    {
        try
        {
            if (session is null || !session.IsOpen)
            {
                await CloseAsync().ConfigureAwait(false);
                session = await ConnectAsync(cancellationToken).ConfigureAwait(false);
                if (session is null)
                {
                    return false;
                }
            }

            var state = await session.EvaluateAsync(StateExpression, cancellationToken).ConfigureAwait(false);
            return state.ValueKind == JsonValueKind.True;
        }
        catch (Exception exception) when (exception is CdpException or System.Net.WebSockets.WebSocketException or HttpRequestException
            or InvalidOperationException or OperationCanceledException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await CloseAsync().ConfigureAwait(false);
            return false;
        }
    }

    private async Task<ICdpEventSession?> ConnectAsync(CancellationToken cancellationToken)
    {
        var targets = await devTools.ListTargetsAsync(cancellationToken).ConfigureAwait(false);
        var shared = targets?.FirstOrDefault(target => target.Title == SteamThemeEngine.SharedContextTitle);
        if (shared is null || await devTools.ConnectAsync(shared, cancellationToken).ConfigureAwait(false) is not ICdpEventSession connected)
        {
            return null;
        }

        connected.EventReceived += OnEvent;
        await connected.SendAsync("Runtime.addBinding", new { name = Binding }, cancellationToken).ConfigureAwait(false);
        return connected;
    }

    private void OnEvent(string method, JsonElement parameters)
    {
        if (method == "Runtime.bindingCalled"
            && parameters.ValueKind == JsonValueKind.Object
            && parameters.TryGetProperty("name", out var name)
            && name.ValueEquals(Binding))
        {
            wake.Release();
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

    private void Apply(bool wanted)
    {
        try
        {
            var processes = mixer.Processes();
            using var scan = mixer.Scan(processes);
            var decisions = policy.Decide(wanted, scan.Sessions, processId => SteamGameProcesses.IsGame(processes, processId));
            var changed = new List<string>();
            for (var index = 0; index < decisions.Count; index++)
            {
                if (decisions[index] is not { } muted)
                {
                    continue;
                }

                scan.SetMute(index, muted);
                changed.Add(scan.Sessions[index].Executable);
            }

            if (changed.Count > 0)
            {
                CompanionLog.Write("themes.game_audio", $"{(wanted ? "silenced" : "restored")} {string.Join(", ", changed.Distinct(StringComparer.OrdinalIgnoreCase))}");
            }
        }
        catch (Exception exception) when (exception is System.Runtime.InteropServices.COMException or InvalidCastException or UnauthorizedAccessException)
        {
            CompanionLog.Write("themes.game_audio", exception);
        }
    }
}
