using System.Globalization;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

public sealed record ForegroundProcess(IntPtr Window, int ProcessId, string? Image);

/// <summary>The window in front and the image of the process that owns it.</summary>
[SupportedOSPlatform("windows")]
public static class ForegroundProcessReader
{
    public static ForegroundProcess? Read()
    {
        var window = GetForegroundWindow();
        if (window == IntPtr.Zero)
        {
            return null;
        }

        GetWindowThreadProcessId(window, out var processId);
        return processId == 0 ? null : new ForegroundProcess(window, (int)processId, RunningImages.ImagePath((int)processId));
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
}

/// <summary>
/// Keeps the in-game badge up to date: about once a second it looks at the window in front, and while that is a game
/// with a Panel upscaler it reads that game's logs every couple of seconds and hands the lines to the overlay window.
/// </summary>
public sealed class InGameBadgeService
{
    public static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(1);
    public static readonly TimeSpan FactsInterval = TimeSpan.FromSeconds(2);
    public static readonly TimeSpan RootsInterval = TimeSpan.FromSeconds(20);

    private readonly UpscalerStateStore store;
    private readonly UpscalerData data;
    private readonly Func<IReadOnlyDictionary<string, string>> gameRoots;
    private readonly IInGameOverlay overlay;
    private readonly Func<ForegroundProcess?> foreground;
    private readonly InGameFactsReader reader;
    private readonly Func<DateTimeOffset> now;
    private readonly InGameText text;
    private readonly InGameBadgePolicy policy = new();

    private IReadOnlyDictionary<string, string> roots = new Dictionary<string, string>();
    private DateTimeOffset rootsAt = DateTimeOffset.MinValue;
    private string? factsFor;
    private int startedFor = -1;
    private double started;
    private DateTimeOffset factsAt = DateTimeOffset.MinValue;
    private InGameFacts? facts;
    private bool reported;

    /// <param name="gameRoots">Each installed game's Steam folder by app id.</param>
    public InGameBadgeService(
        UpscalerStateStore store,
        UpscalerData data,
        Func<IReadOnlyDictionary<string, string>> gameRoots,
        IInGameOverlay overlay,
        Func<ForegroundProcess?> foreground,
        InGameFactsReader reader,
        Func<DateTimeOffset>? now = null,
        InGameText? text = null)
    {
        this.store = store;
        this.data = data;
        this.gameRoots = gameRoots;
        this.overlay = overlay;
        this.foreground = foreground;
        this.reader = reader;
        this.now = now ?? (() => DateTimeOffset.UtcNow);
        this.text = text ?? InGameText.ForCulture(CultureInfo.CurrentUICulture);
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(PollInterval, cancellationToken).ConfigureAwait(false);
                await Task.Run(Tick, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                if (!reported)
                {
                    reported = true;
                    CompanionLog.Write("upscalers.ingame", exception);
                }
            }
        }

        overlay.Present(null);
    }

    public void Tick()
    {
        var mode = store.InGameMode;
        var current = mode == InGameModes.Off ? null : foreground();
        var appId = current?.Image is { } image ? GameOf(image) : null;
        var stored = appId is null ? null : store.Install(appId);
        if (current is null || appId is null || stored is null)
        {
            overlay.Present(null);
            return;
        }

        var time = now();
        var run = appId + ":" + current.ProcessId.ToString(CultureInfo.InvariantCulture);
        if (!policy.CanShow(time, mode, run))
        {
            overlay.Present(null);
            return;
        }

        if (factsFor != run || time - factsAt >= FactsInterval)
        {
            facts = reader.Read(stored, data.Catalog.Build(stored.Install.Build), time, StartedAt(current.ProcessId));
            factsFor = run;
            factsAt = time;
        }

        var hasContent = InGameContent.HasContent(facts);
        var visible = policy.Visible(time, mode, run, hasContent);
        overlay.Present(visible && facts is not null ? new OverlayFrame(InGameContent.Lines(facts, text), current.Window) : null);
    }

    private double StartedAt(int processId)
    {
        if (startedFor == processId)
        {
            return started;
        }

        startedFor = processId;
        try
        {
            using var process = System.Diagnostics.Process.GetProcessById(processId);
            started = new DateTimeOffset(process.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0;
        }
        catch (Exception exception) when (exception is ArgumentException or InvalidOperationException or System.ComponentModel.Win32Exception or NotSupportedException)
        {
            started = 0;
        }

        return started;
    }

    private string? GameOf(string image)
    {
        var time = now();
        if (time - rootsAt >= RootsInterval)
        {
            roots = gameRoots();
            rootsAt = time;
        }

        foreach (var (appId, root) in roots)
        {
            if (GameGuards.IsRunningUnder(root, new[] { image }))
            {
                return appId;
            }
        }

        return null;
    }
}
