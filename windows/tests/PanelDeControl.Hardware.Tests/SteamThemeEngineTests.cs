using System.Text.Json;
using System.Text.RegularExpressions;
using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class SteamThemeEngineTests : IDisposable
{
    private const string BigPictureUrl = "about:blank?browserType=3&useragent=Valve%20Steam%20Gamepad";

    private readonly string root = Path.Combine(Path.GetTempPath(), $"pdc-engine-{Guid.NewGuid():N}");
    private readonly FakeDevTools devTools = new();
    private readonly FakeSteam steam = new();

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task ReportsWhyThemesCannotReachSteam()
    {
        var engine = Engine(Theme());

        steam.Path = null;
        Assert.Equal(SteamThemeConnection.SteamNotInstalled, (await engine.CycleAsync(default)).Connection);

        steam.Path = root;
        devTools.Targets = null;
        steam.Debugging = false;
        Assert.Equal(SteamThemeConnection.DebuggingOff, (await engine.CycleAsync(default)).Connection);

        steam.Debugging = true;
        steam.Running = true;
        Assert.Equal(SteamThemeConnection.RestartRequired, (await engine.CycleAsync(default)).Connection);

        steam.Running = false;
        Assert.Equal(SteamThemeConnection.SteamNotRunning, (await engine.CycleAsync(default)).Connection);
    }

    [Fact]
    public async Task AppliesEachPageAndReadsItBack()
    {
        devTools.Targets = new[] { Page("bp", "Modo Big Picture de Steam", BigPictureUrl), Page("qam", "QuickAccess_uid2"), Page("menu", "MainMenu_uid2") };
        var engine = Engine(Theme());

        var status = await engine.CycleAsync(default);

        Assert.Equal(SteamThemeConnection.Connected, status.Connection);
        Assert.Equal(2, devTools.Pages["bp"].Sheets.Count);
        Assert.Single(devTools.Pages["qam"].Sheets);
        Assert.False(devTools.Pages.ContainsKey("menu"));
        Assert.Equal(new ThemeApplication(2, 2, false, false), status.Themes["Hooandee Eclipse"]);
    }

    [Fact]
    public async Task OnlyProbesWhenNothingChangedAndRepaintsAReloadedPage()
    {
        devTools.Targets = new[] { Page("bp", "SP", BigPictureUrl) };
        var engine = Engine(Theme());
        await engine.CycleAsync(default);
        var page = devTools.Pages["bp"];

        await engine.CycleAsync(default);
        Assert.Equal(1, page.Applies);

        page.Reload();
        var status = await engine.CycleAsync(default);

        Assert.Equal(2, page.Applies);
        Assert.Equal(2, page.Sheets.Count);
        Assert.Equal(1, status.Themes["Hooandee Eclipse"].PagesApplied);
    }

    [Fact]
    public async Task ReportsAPartialPageAsNotApplied()
    {
        devTools.Targets = new[] { Page("bp", "SP", BigPictureUrl) };
        devTools.DropOneSheet = true;
        var engine = Engine(Theme());

        var status = await engine.CycleAsync(default);

        Assert.Equal(new ThemePageStatus("SP", 2, 1), Assert.Single(status.Pages));
        Assert.Equal(0, status.Themes["Hooandee Eclipse"].PagesApplied);
    }

    [Fact]
    public async Task TranslatesClassesToTheLiveClient()
    {
        devTools.Targets = new[] { Shared(), Page("bp", "SP", BigPictureUrl) };
        devTools.LiveClasses = new[] { "_live" };
        var table = ClassTranslator.ParseTable("""{"x":["Home_Card","_live","_future"]}""");
        var engine = Engine(Theme(), new FixedTable(table));

        await engine.CycleAsync(default);

        Assert.Contains("._live{", devTools.Pages["bp"].Sheets["pdc-theme:Hooandee Eclipse:home.css"]);
    }

    [Fact]
    public async Task LoadsTheRuntimeHostAndReportsMountedExtensions()
    {
        devTools.Targets = new[] { Shared(), Page("bp", "SP", BigPictureUrl) };
        var engine = Engine(Theme(), extension: true);

        var status = await engine.CycleAsync(default);

        Assert.Equal(1, devTools.HostLoads);
        Assert.True(status.Host.Present);
        Assert.Equal(new[] { "hooandee-eclipse@0.2.5" }, status.Host.Mounted);
        Assert.True(status.Themes["Hooandee Eclipse"].RuntimeMounted);

        await engine.CycleAsync(default);
        Assert.Equal(1, devTools.HostUpdates);

        devTools.ResetHost();
        await engine.CycleAsync(default);
        Assert.Equal(2, devTools.HostLoads);
        Assert.Equal(2, devTools.HostUpdates);
    }

    [Fact]
    public async Task DisablingEveryThemeCleansThePagesItPainted()
    {
        devTools.Targets = new[] { Page("bp", "SP", BigPictureUrl) };
        var enabled = true;
        var theme = Theme();
        var engine = new SteamThemeEngine(
            devTools,
            steam,
            () => Inputs(enabled ? new[] { new ThemeSelection(theme, new Dictionary<string, string>()) } : Array.Empty<ThemeSelection>()),
            () => "host",
            new FixedTable(null));
        await engine.CycleAsync(default);

        enabled = false;
        await engine.InvalidateAndCycleAsync();

        Assert.Empty(devTools.Pages["bp"].Sheets);
    }

    private SteamThemeEngine Engine(InstalledTheme theme, IClassTableSource? table = null, bool extension = false) => new(
        devTools,
        steam,
        () => Inputs(new[] { new ThemeSelection(theme, new Dictionary<string, string>()) }, extension),
        () => "host-bundle",
        table ?? new FixedTable(null));

    private static ThemeEngineInputs Inputs(IReadOnlyList<ThemeSelection> enabled, bool extension = false) => new(
        enabled,
        extension
            ? new[] { new ThemeHostExtension("hooandee-eclipse", "Hooandee Eclipse", "0.2.5", 2, new string('a', 64), "module.exports = {}") }
            : Array.Empty<ThemeHostExtension>(),
        """{"status":"ready","themes":[]}""");

    private InstalledTheme Theme()
    {
        var directory = Path.Combine(root, "Hooandee Eclipse");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "tokens.css"), ":root{--x:1}");
        File.WriteAllText(Path.Combine(directory, "home.css"), ".Home_Card{color:red}");
        var manifest = ThemeManifest.Parse("""
            {"name":"Hooandee Eclipse","version":"0.2.5",
             "inject":{"tokens.css":["bigpicture","QuickAccess"],"home.css":["bigpicture"]}}
            """);
        return new InstalledTheme(manifest, null, directory);
    }

    private DevToolsTarget Page(string id, string title, string url = "about:blank") =>
        new(id, title, url, "page", $"ws://127.0.0.1:8080/devtools/page/{id}");

    private DevToolsTarget Shared() => Page("shared", SteamThemeEngine.SharedContextTitle, "https://steamloopback.host/routes/library/home");

    private sealed class FixedTable : IClassTableSource
    {
        private readonly IReadOnlyList<IReadOnlyList<string>>? table;

        public FixedTable(IReadOnlyList<IReadOnlyList<string>>? table) => this.table = table;

        public IReadOnlyList<IReadOnlyList<string>>? Current(bool betaClient) => table;
    }

    private sealed class FakeSteam : ISteamInstallation
    {
        public string? Path { get; set; } = "/steam";

        public bool Debugging { get; set; } = true;

        public bool Running { get; set; } = true;

        public string? SteamPath => Path;

        public bool DebuggingEnabled => Debugging;

        public bool BetaClient => false;

        public bool IsRunning => Running;

        public void EnableDebugging() => Debugging = true;

        public Task RestartAsync(bool bigPicture, CancellationToken cancellationToken) => Task.CompletedTask;
    }

    private sealed class FakePage
    {
        public Dictionary<string, string> Sheets { get; } = new();

        public string? Fingerprint { get; set; }

        public int Applies { get; set; }

        public void Reload()
        {
            Sheets.Clear();
            Fingerprint = null;
        }
    }

    private sealed class FakeDevTools : ISteamDevTools
    {
        private static readonly Regex FingerprintAssignment = new(@"__pdcThemeFingerprint = ""([0-9A-F]+)""");
        private static readonly Regex FingerprintProbe = new(@"__pdcThemeFingerprint === ""([0-9A-F]+)""");

        private bool hostPresent;
        private long hostRevision;

        public IReadOnlyList<DevToolsTarget>? Targets { get; set; } = Array.Empty<DevToolsTarget>();

        public Dictionary<string, FakePage> Pages { get; } = new();

        public bool DropOneSheet { get; set; }

        public string[] LiveClasses { get; set; } = Array.Empty<string>();

        public int HostLoads { get; private set; }

        public int HostUpdates { get; private set; }

        public void ResetHost()
        {
            hostPresent = false;
            hostRevision = 0;
        }

        public Task<IReadOnlyList<DevToolsTarget>?> ListTargetsAsync(CancellationToken cancellationToken) => Task.FromResult(Targets);

        public Task<ICdpSession> ConnectAsync(DevToolsTarget target, CancellationToken cancellationToken) =>
            Task.FromResult<ICdpSession>(new Session(this, target.Id));

        private JsonElement Evaluate(string id, string expression)
        {
            if (expression.Contains("webpackChunksteamui", StringComparison.Ordinal))
            {
                return Json(JsonSerializer.Serialize(LiveClasses));
            }

            if (expression == "host-bundle" || expression == "host")
            {
                HostLoads++;
                hostPresent = true;
                return default;
            }

            if (expression.Contains("?.hostVersion", StringComparison.Ordinal))
            {
                return hostPresent ? Json("1") : Json("null");
            }

            if (expression.Contains("?.status()", StringComparison.Ordinal))
            {
                return hostPresent ? HostStatus() : Json("null");
            }

            if (expression.Contains("__pdcWindowsThemeHost.update(", StringComparison.Ordinal))
            {
                HostUpdates++;
                var revision = Regex.Match(expression, @"""revision"":(\d+)");
                hostRevision = long.Parse(revision.Groups[1].Value);
                return HostStatus();
            }

            var page = Pages.TryGetValue(id, out var existing) ? existing : Pages[id] = new FakePage();
            var probe = FingerprintProbe.Match(expression);
            if (probe.Success && !expression.Contains("const sheets", StringComparison.Ordinal))
            {
                return Json(probe.Groups[1].Value == page.Fingerprint ? page.Sheets.Count.ToString() : "-1");
            }

            var sheetsJson = Regex.Match(expression, @"const sheets = (\[.*?\]);", RegexOptions.Singleline).Groups[1].Value;
            using var sheets = JsonDocument.Parse(sheetsJson);
            page.Sheets.Clear();
            foreach (var sheet in sheets.RootElement.EnumerateArray().Skip(DropOneSheet ? 1 : 0))
            {
                page.Sheets[sheet.GetProperty("id").GetString()!] = sheet.GetProperty("css").GetString()!;
            }

            page.Fingerprint = FingerprintAssignment.Match(expression).Groups[1].Value;
            page.Applies++;
            return Json($$"""{"applied":{{page.Sheets.Count}},"classes":[]}""");
        }

        private JsonElement HostStatus() => Json($$"""
            {"hostVersion":1,"revision":{{hostRevision}},"steamDocument":true,"qamDocument":true,
             "mounted":{{(hostRevision > 0 ? "[\"hooandee-eclipse@0.2.5\"]" : "[]")}},"errors":[]}
            """);

        private static JsonElement Json(string json)
        {
            using var document = JsonDocument.Parse(json);
            return document.RootElement.Clone();
        }

        private sealed class Session : ICdpSession
        {
            private readonly FakeDevTools owner;
            private readonly string id;

            public Session(FakeDevTools owner, string id)
            {
                this.owner = owner;
                this.id = id;
            }

            public bool IsOpen => true;

            public Task<JsonElement> EvaluateAsync(string expression, CancellationToken cancellationToken) =>
                Task.FromResult(owner.Evaluate(id, expression));

            public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        }
    }
}

internal static class SteamThemeEngineTestExtensions
{
    public static async Task<ThemeEngineStatus> InvalidateAndCycleAsync(this SteamThemeEngine engine)
    {
        _ = engine.InvalidateAsync(CancellationToken.None);
        return await engine.CycleAsync(default);
    }
}
