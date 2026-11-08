using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Windows has no SIGSTOP, so a theme that freezes the running game while its menus are over it (games.pause) asks
/// the theme host, which keeps a lease that ends by itself (gamePause.ts), and this suspends the game's processes
/// while the lease lasts. A DevTools binding wakes it the moment the lease starts or ends; the lease itself is always
/// read from the host. The game only stays frozen while Big Picture is the window in front: the moment the game
/// is (or anything else is), Steam or the host goes, or the companion stops, every process frozen here runs again.
/// </summary>
public sealed class GameFreezer
{
    private const string Binding = "pdcHostGamePause";
    private const string StateExpression = "typeof window.__pdcWindowsThemeHost?.status?.().gamePaused === 'string'";
    private static readonly TimeSpan ActivePoll = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan IdlePoll = TimeSpan.FromSeconds(2);
    // A game can start more processes while it is frozen (a launcher handing over to the game).
    private static readonly TimeSpan Rescan = TimeSpan.FromSeconds(1);

    private readonly ISteamDevTools devTools;
    private readonly Func<IReadOnlyDictionary<int, ProcessEntry>> processes;
    private readonly GameFreezePolicy policy;
    private readonly SemaphoreSlim wake = new(0);
    private readonly Func<bool> bigPictureInFront;
    private ICdpEventSession? session;

    public GameFreezer(ISteamDevTools devTools, Func<IReadOnlyDictionary<int, ProcessEntry>> processes, GameFreezePolicy policy, Func<bool> bigPictureInFront)
    {
        this.devTools = devTools;
        this.processes = processes;
        this.policy = policy;
        this.bigPictureInFront = bigPictureInFront;
    }

    public static string DefaultStatePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "game-frozen.json");

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            // A previous companion that stopped with a game frozen left it on disk: it runs again first.
            Thaw("restored");
            var scannedAt = DateTimeOffset.MinValue;
            while (!cancellationToken.IsCancellationRequested)
            {
                var requested = await ReadStateAsync(cancellationToken).ConfigureAwait(false);
                if (requested && bigPictureInFront())
                {
                    var now = DateTimeOffset.UtcNow;
                    if (!policy.HasFrozen || now - scannedAt >= Rescan)
                    {
                        Freeze();
                        scannedAt = now;
                    }
                }
                else if (policy.HasFrozen)
                {
                    Thaw("thawed");
                }

                await wake.WaitAsync(requested || policy.HasFrozen ? ActivePoll : IdlePoll, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            Thaw("thawed");
            await CloseAsync().ConfigureAwait(false);
        }
    }

    private void Freeze()
    {
        try
        {
            var added = policy.Freeze(processes());
            if (added.Count > 0)
            {
                CompanionLog.Write("themes.game_freeze", $"frozen {Describe(added)}");
            }
        }
        catch (Exception exception) when (exception is Win32Exception or UnauthorizedAccessException or InvalidOperationException)
        {
            CompanionLog.Write("themes.game_freeze", exception);
        }
    }

    private void Thaw(string verb)
    {
        if (!policy.HasFrozen)
        {
            return;
        }

        var resumed = policy.Thaw();
        CompanionLog.Write("themes.game_freeze", $"{verb} {Describe(resumed)}");
    }

    private static string Describe(IReadOnlyList<FrozenProcess> list) =>
        list.Count == 0 ? "nothing" : string.Join(", ", list.Select(process => $"{process.Executable}#{process.ProcessId}"));

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
}

/// <summary>NtSuspendProcess / NtResumeProcess: every thread of the process at once, as Resource Monitor does.</summary>
[SupportedOSPlatform("windows")]
public sealed class NtGameProcessSuspender : IGameProcessSuspender
{
    private const uint ProcessSuspendResume = 0x0800;
    private const uint ProcessQueryLimitedInformation = 0x1000;

    public long? StartTicks(int processId)
    {
        var handle = OpenProcess(ProcessQueryLimitedInformation, false, processId);
        if (handle == IntPtr.Zero)
        {
            return null;
        }

        try
        {
            return GetProcessTimes(handle, out var creation, out _, out _, out _) ? creation : null;
        }
        finally
        {
            CloseHandle(handle);
        }
    }

    public bool Suspend(int processId) => Call(processId, NtSuspendProcess);

    public bool Resume(int processId) => Call(processId, NtResumeProcess);

    private static bool Call(int processId, Func<IntPtr, int> call)
    {
        var handle = OpenProcess(ProcessSuspendResume, false, processId);
        if (handle == IntPtr.Zero)
        {
            return false;
        }

        try
        {
            return call(handle) >= 0;
        }
        finally
        {
            CloseHandle(handle);
        }
    }

    [DllImport("ntdll.dll")]
    private static extern int NtSuspendProcess(IntPtr process);

    [DllImport("ntdll.dll")]
    private static extern int NtResumeProcess(IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetProcessTimes(IntPtr process, out long creation, out long exit, out long kernel, out long user);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);
}
