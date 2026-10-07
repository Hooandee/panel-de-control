using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

public enum SteamThemeConnection
{
    SteamNotInstalled,
    DebuggingOff,
    SteamNotRunning,
    RestartRequired,
    WaitingForBigPicture,
    Connected,
}

public sealed record ThemePageStatus(string Title, int Expected, int Applied);

public sealed record ThemeHostStatus(bool Present, bool SteamDocument, IReadOnlyList<string> Mounted, IReadOnlyList<string> Errors);

public sealed record ThemeEngineStatus(
    long Cycle,
    SteamThemeConnection Connection,
    IReadOnlyList<ThemePageStatus> Pages,
    ThemeHostStatus Host,
    IReadOnlyDictionary<string, ThemeApplication> Themes,
    string? LastError)
{
    public long InputsGeneration { get; init; }

    public static ThemeEngineStatus Initial { get; } = new(
        0,
        SteamThemeConnection.SteamNotRunning,
        Array.Empty<ThemePageStatus>(),
        new ThemeHostStatus(false, false, Array.Empty<string>(), Array.Empty<string>()),
        new Dictionary<string, ThemeApplication>(),
        null);
}

/// <summary>Readback of one enabled theme across every Steam page it targets.</summary>
public sealed record ThemeApplication(int PagesExpected, int PagesApplied, bool RuntimeExpected, bool RuntimeMounted);

public sealed record ThemeEngineInputs(
    IReadOnlyList<ThemeSelection> Enabled,
    IReadOnlyList<ThemeHostExtension> Extensions,
    string SnapshotJson);

public sealed record ThemeHostExtension(string CatalogId, string CssLoaderName, string Version, int AbiVersion, string Sha256, string Source);

/// <summary>
/// Keeps Steam's pages in the state the settings describe. It never trusts its own writes:
/// every cycle reads each page back, and a page Steam reloaded is detected and repainted.
/// </summary>
public sealed class SteamThemeEngine
{
    public const string SharedContextTitle = "SharedJSContext";
    private const string FingerprintGlobal = "__pdcThemeFingerprint";
    private const string HostGlobal = "__pdcWindowsThemeHost";

    private static readonly TimeSpan CycleInterval = TimeSpan.FromSeconds(2);

    private readonly ISteamDevTools devTools;
    private readonly ISteamInstallation steam;
    private readonly Func<ThemeEngineInputs> loadInputs;
    private readonly Func<string> hostBundle;
    private readonly IClassTableSource classTable;
    private readonly Dictionary<string, PageSession> pages = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> cssCache = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim wake = new(0, int.MaxValue);
    private readonly object statusGate = new();
    private ThemeEngineInputs? inputs;
    private long requestedGeneration = 1;
    private long loadedGeneration;
    private ClassTranslator translator = ClassTranslator.Identity;
    private IReadOnlySet<string>? liveClasses;
    private string? liveClassesSession;
    private long hostRevision;
    private string? hostInputsFingerprint;
    private ThemeEngineStatus status = ThemeEngineStatus.Initial;
    private TaskCompletionSource<ThemeEngineStatus> nextCycle = NewCycleSignal();

    public SteamThemeEngine(
        ISteamDevTools devTools,
        ISteamInstallation steam,
        Func<ThemeEngineInputs> loadInputs,
        Func<string> hostBundle,
        IClassTableSource classTable)
    {
        this.devTools = devTools;
        this.steam = steam;
        this.loadInputs = loadInputs;
        this.hostBundle = hostBundle;
        this.classTable = classTable;
    }

    public ThemeEngineStatus Status
    {
        get
        {
            lock (statusGate)
            {
                return status;
            }
        }
    }

    /// <summary>
    /// Reloads settings and library now and completes with the first cycle that used them.
    /// </summary>
    public async Task<ThemeEngineStatus> InvalidateAsync(CancellationToken cancellationToken)
    {
        var generation = Interlocked.Increment(ref requestedGeneration);
        wake.Release();
        while (true)
        {
            Task<ThemeEngineStatus> next;
            lock (statusGate)
            {
                if (status.InputsGeneration >= generation)
                {
                    return status;
                }

                next = nextCycle.Task;
            }

            await next.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                ThemeEngineStatus result;
                try
                {
                    result = await CycleAsync(cancellationToken).ConfigureAwait(false);
                }
                catch (Exception exception) when (exception is not OperationCanceledException)
                {
                    CompanionLog.Write("themes.cycle", exception);
                    result = Status with { LastError = exception.GetType().Name };
                }

                Publish(result with { InputsGeneration = loadedGeneration });
                await wake.WaitAsync(CycleInterval, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
        finally
        {
            foreach (var page in pages.Values)
            {
                await page.Session.DisposeAsync().ConfigureAwait(false);
            }

            pages.Clear();
        }
    }

    internal async Task<ThemeEngineStatus> CycleAsync(CancellationToken cancellationToken)
    {
        var cycle = Status.Cycle + 1;
        var generation = Interlocked.Read(ref requestedGeneration);
        if (inputs is null || generation != loadedGeneration)
        {
            loadedGeneration = generation;
            inputs = null;
            cssCache.Clear();
            inputs = loadInputs();
        }

        var current = inputs;
        if (steam.SteamPath is null)
        {
            return Disconnected(cycle, SteamThemeConnection.SteamNotInstalled, current);
        }

        var targets = await devTools.ListTargetsAsync(cancellationToken).ConfigureAwait(false);
        if (targets is null)
        {
            await DropAllAsync().ConfigureAwait(false);
            var connection = !steam.DebuggingEnabled
                ? SteamThemeConnection.DebuggingOff
                : steam.IsRunning ? SteamThemeConnection.RestartRequired : SteamThemeConnection.SteamNotRunning;
            return Disconnected(cycle, connection, current);
        }

        var live = targets.Where(target => target.Type == "page" && target.WebSocketUrl.Length > 0).ToArray();
        foreach (var gone in pages.Keys.Except(live.Select(target => target.Id)).ToArray())
        {
            await DropAsync(gone).ConfigureAwait(false);
        }

        string? lastError = null;
        var shared = live.FirstOrDefault(target => target.Title == SharedContextTitle);
        var host = new ThemeHostStatus(false, false, Array.Empty<string>(), Array.Empty<string>());
        if (shared is not null)
        {
            try
            {
                var session = await SessionAsync(shared, cancellationToken).ConfigureAwait(false);
                await RefreshTranslatorAsync(shared.Id, session, cancellationToken).ConfigureAwait(false);
                host = await SyncHostAsync(session, current, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is CdpException or OperationCanceledException or System.Net.WebSockets.WebSocketException)
            {
                cancellationToken.ThrowIfCancellationRequested();
                lastError = "host_unavailable";
                await DropAsync(shared.Id).ConfigureAwait(false);
            }
        }

        var pageStatuses = new List<ThemePageStatus>();
        var applied = current.Enabled.ToDictionary(selection => selection.Theme.Name, _ => (expected: 0, applied: 0), StringComparer.Ordinal);
        var bigPictureSeen = false;
        foreach (var target in live.Where(target => target.Title != SharedContextTitle))
        {
            var steamTarget = new SteamTarget(target.Id, target.Title, target.Url, pages.TryGetValue(target.Id, out var known) ? known.Classes : new HashSet<string>());
            bigPictureSeen |= ThemeTargetMatcher.IsBigPicture(steamTarget);
            var sheets = ThemeComposer.SheetsFor(steamTarget, current.Enabled);
            if (sheets.Count == 0 && !pages.ContainsKey(target.Id))
            {
                continue;
            }

            try
            {
                var session = await SessionAsync(target, cancellationToken).ConfigureAwait(false);
                var count = await SyncPageAsync(target, session, sheets, cancellationToken).ConfigureAwait(false);
                pageStatuses.Add(new ThemePageStatus(target.Title, sheets.Count, count));
                foreach (var theme in sheets.Select(sheet => sheet.ThemeName).Distinct())
                {
                    var entry = applied[theme];
                    applied[theme] = (entry.expected + 1, entry.applied + (count == sheets.Count ? 1 : 0));
                }
            }
            catch (Exception exception) when (exception is CdpException or OperationCanceledException or System.Net.WebSockets.WebSocketException or IOException)
            {
                cancellationToken.ThrowIfCancellationRequested();
                lastError = "page_unavailable";
                pageStatuses.Add(new ThemePageStatus(target.Title, sheets.Count, 0));
                await DropAsync(target.Id).ConfigureAwait(false);
            }
        }

        var themes = current.Enabled.ToDictionary(
            selection => selection.Theme.Name,
            selection =>
            {
                var extension = current.Extensions.FirstOrDefault(candidate => candidate.CssLoaderName == selection.Theme.Name);
                var mounted = extension is not null && host.Mounted.Contains($"{extension.CatalogId}@{extension.Version}");
                return new ThemeApplication(applied[selection.Theme.Name].expected, applied[selection.Theme.Name].applied, extension is not null, mounted);
            },
            StringComparer.Ordinal);
        return new ThemeEngineStatus(
            cycle,
            bigPictureSeen ? SteamThemeConnection.Connected : SteamThemeConnection.WaitingForBigPicture,
            pageStatuses,
            host,
            themes,
            lastError);
    }

    private ThemeEngineStatus Disconnected(long cycle, SteamThemeConnection connection, ThemeEngineInputs current) => new(
        cycle,
        connection,
        Array.Empty<ThemePageStatus>(),
        new ThemeHostStatus(false, false, Array.Empty<string>(), Array.Empty<string>()),
        current.Enabled.ToDictionary(
            selection => selection.Theme.Name,
            selection => new ThemeApplication(0, 0, selection.Theme.Marker?.Extension is not null, false),
            StringComparer.Ordinal),
        null);

    private void Publish(ThemeEngineStatus result)
    {
        TaskCompletionSource<ThemeEngineStatus> completed;
        lock (statusGate)
        {
            status = result;
            completed = nextCycle;
            nextCycle = NewCycleSignal();
        }

        completed.TrySetResult(result);
    }

    private async Task<ICdpSession> SessionAsync(DevToolsTarget target, CancellationToken cancellationToken)
    {
        if (pages.TryGetValue(target.Id, out var existing))
        {
            if (existing.Session.IsOpen)
            {
                return existing.Session;
            }

            await DropAsync(target.Id).ConfigureAwait(false);
        }

        var session = await devTools.ConnectAsync(target, cancellationToken).ConfigureAwait(false);
        pages[target.Id] = new PageSession(session);
        return session;
    }

    private async Task<int> SyncPageAsync(DevToolsTarget target, ICdpSession session, IReadOnlyList<ThemeSheet> sheets, CancellationToken cancellationToken)
    {
        var page = pages[target.Id];
        var css = sheets.Select(sheet => new { id = sheet.Id, css = Css(sheet) }).ToArray();
        var fingerprint = Fingerprint(string.Join('\n', css.Select(sheet => sheet.id + "\0" + sheet.css)));
        var probe = await session.EvaluateAsync(
            $$"""(() => window.{{FingerprintGlobal}} === {{JsonSerializer.Serialize(fingerprint)}} ? document.head?.querySelectorAll("style[data-pdc-theme]").length ?? -1 : -1)()""",
            cancellationToken).ConfigureAwait(false);
        if (probe.ValueKind == JsonValueKind.Number && probe.GetInt32() == sheets.Count)
        {
            return sheets.Count;
        }

        var result = await session.EvaluateAsync(ApplyScript(JsonSerializer.Serialize(css), fingerprint), cancellationToken).ConfigureAwait(false);
        if (result.ValueKind != JsonValueKind.Object)
        {
            return 0;
        }

        page.Classes = result.TryGetProperty("classes", out var classes) && classes.ValueKind == JsonValueKind.Array
            ? classes.EnumerateArray().Select(value => value.GetString() ?? string.Empty).Where(value => value.Length > 0).ToHashSet(StringComparer.Ordinal)
            : page.Classes;
        return result.TryGetProperty("applied", out var count) && count.ValueKind == JsonValueKind.Number ? count.GetInt32() : 0;
    }

    // Same DOM shape as CSS Loader (style.css-loader-style, file text verbatim) because theme
    // runtimes find and budget their own sheets by it. Text is only rewritten when it changed so a
    // runtime that disabled a sheet or swapped rules keeps its work.
    private static string ApplyScript(string sheetsJson, string fingerprint) => $$"""
        (() => {
          const sheets = {{sheetsJson}};
          const head = document.head;
          if (!head) return null;
          const wanted = new Set(sheets.map((sheet) => sheet.id));
          for (const style of [...head.querySelectorAll("style[data-pdc-theme]")]) {
            if (!wanted.has(style.id)) style.remove();
          }
          const ordered = [];
          for (const sheet of sheets) {
            let style = document.getElementById(sheet.id);
            if (!(style instanceof HTMLStyleElement)) {
              style = document.createElement("style");
              style.id = sheet.id;
              style.className = "css-loader-style";
              style.dataset.pdcTheme = "";
              head.append(style);
            }
            if (style.textContent !== sheet.css) style.textContent = sheet.css;
            ordered.push(style);
          }
          const current = [...head.querySelectorAll("style[data-pdc-theme]")];
          if (current.some((style, index) => style !== ordered[index])) {
            for (const style of ordered) head.append(style);
          }
          window.{{FingerprintGlobal}} = {{JsonSerializer.Serialize(fingerprint)}};
          const classes = [...document.documentElement.classList, ...(document.body?.classList ?? [])];
          return { applied: head.querySelectorAll("style[data-pdc-theme]").length, classes };
        })()
        """;

    private async Task<ThemeHostStatus> SyncHostAsync(ICdpSession session, ThemeEngineInputs current, CancellationToken cancellationToken)
    {
        var version = await session.EvaluateAsync($"window.{HostGlobal}?.hostVersion ?? null", cancellationToken).ConfigureAwait(false);
        if (version.ValueKind != JsonValueKind.Number)
        {
            await session.EvaluateAsync(hostBundle(), cancellationToken).ConfigureAwait(false);
            hostInputsFingerprint = null;
        }

        var inputsFingerprint = Fingerprint(current.SnapshotJson + "\0" + string.Join('\n', current.Extensions.Select(extension => extension.Sha256)));
        JsonElement result;
        var reported = await session.EvaluateAsync($"window.{HostGlobal}?.status() ?? null", cancellationToken).ConfigureAwait(false);
        if (hostInputsFingerprint != inputsFingerprint || HostRevision(reported) < hostRevision)
        {
            hostRevision = Math.Max(hostRevision, HostRevision(reported)) + 1;
            var state = $$"""{"revision":{{hostRevision}},"snapshot":{{current.SnapshotJson}},"extensions":{{JsonSerializer.Serialize(current.Extensions.Select(extension => new
            {
                catalogId = extension.CatalogId,
                cssLoaderName = extension.CssLoaderName,
                version = extension.Version,
                abiVersion = extension.AbiVersion,
                sha256 = extension.Sha256,
                source = extension.Source,
            }))}}}""";
            result = await session.EvaluateAsync($"window.{HostGlobal}.update({state})", cancellationToken).ConfigureAwait(false);
            hostInputsFingerprint = inputsFingerprint;
        }
        else
        {
            result = reported;
        }

        return ReadHostStatus(result);
    }

    private static long HostRevision(JsonElement status) =>
        status.ValueKind == JsonValueKind.Object && status.TryGetProperty("revision", out var revision) && revision.TryGetInt64(out var value)
            ? value
            : -1;

    private static ThemeHostStatus ReadHostStatus(JsonElement status)
    {
        if (status.ValueKind != JsonValueKind.Object)
        {
            return new ThemeHostStatus(false, false, Array.Empty<string>(), Array.Empty<string>());
        }

        static IReadOnlyList<string> Strings(JsonElement element, string name) =>
            element.TryGetProperty(name, out var values) && values.ValueKind == JsonValueKind.Array
                ? values.EnumerateArray().Select(value => value.GetString() ?? string.Empty).ToArray()
                : Array.Empty<string>();

        return new ThemeHostStatus(
            true,
            status.TryGetProperty("steamDocument", out var document) && document.ValueKind == JsonValueKind.True,
            Strings(status, "mounted"),
            Strings(status, "errors"));
    }

    private async Task RefreshTranslatorAsync(string sessionId, ICdpSession session, CancellationToken cancellationToken)
    {
        if (liveClassesSession != sessionId)
        {
            var classes = await session.EvaluateAsync(LiveClassesScript, cancellationToken).ConfigureAwait(false);
            liveClasses = classes.ValueKind == JsonValueKind.Array
                ? classes.EnumerateArray().Select(value => value.GetString() ?? string.Empty).Where(value => value.Length > 0).ToHashSet(StringComparer.Ordinal)
                : null;
            liveClassesSession = sessionId;
        }

        var table = classTable.Current(steam.BetaClient);
        var next = table is null ? ClassTranslator.Identity : ClassTranslator.Create(table, liveClasses);
        if (next.Fingerprint != translator.Fingerprint)
        {
            translator = next;
            cssCache.Clear();
        }
    }

    // Webpack class maps are plain objects whose values are generated class names.
    private const string LiveClassesScript = """
        (() => {
          let require;
          try {
            window.webpackChunksteamui.push([[Symbol("pdc-themes")], {}, (webpackRequire) => { require = webpackRequire; }]);
          } catch {
            return null;
          }
          if (!require?.c) return null;
          const names = new Set();
          const valid = /^[_a-zA-Z][_a-zA-Z0-9-]*$/;
          for (const module of Object.values(require.c)) {
            const exports = module?.exports;
            if (!exports || typeof exports !== "object") continue;
            let values;
            try {
              values = Object.values(exports);
            } catch {
              continue;
            }
            if (values.length === 0 || values.length > 2000 || !values.every((value) => typeof value === "string")) continue;
            for (const value of values) {
              for (const name of value.split(" ")) if (valid.test(name)) names.add(name);
            }
          }
          return [...names];
        })()
        """;

    private string Css(ThemeSheet sheet)
    {
        var key = sheet.Id;
        if (cssCache.TryGetValue(key, out var cached))
        {
            return cached;
        }

        var theme = inputs!.Enabled.First(selection => selection.Theme.Name == sheet.ThemeName).Theme;
        var path = Path.Combine(theme.Directory, sheet.File.Replace('/', Path.DirectorySeparatorChar));
        var css = translator.Translate(File.ReadAllText(path));
        cssCache[key] = css;
        return css;
    }

    private static string Fingerprint(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)))[..24];

    private async Task DropAsync(string id)
    {
        if (pages.Remove(id, out var page))
        {
            await page.Session.DisposeAsync().ConfigureAwait(false);
        }

        if (id == liveClassesSession)
        {
            liveClassesSession = null;
        }
    }

    private async Task DropAllAsync()
    {
        foreach (var id in pages.Keys.ToArray())
        {
            await DropAsync(id).ConfigureAwait(false);
        }

        hostInputsFingerprint = null;
    }

    private static TaskCompletionSource<ThemeEngineStatus> NewCycleSignal() =>
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    private sealed class PageSession
    {
        public PageSession(ICdpSession session)
        {
            Session = session;
        }

        public ICdpSession Session { get; }

        public IReadOnlySet<string> Classes { get; set; } = new HashSet<string>();
    }
}
