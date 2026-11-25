using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class InGameBadgeServiceTests : IDisposable
{
    private static readonly UpscalerData Data = UpscalerData.LoadEmbedded();
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-ingame-service-" + Guid.NewGuid().ToString("N"));
    private readonly string game;
    private readonly UpscalerStateStore store;
    private readonly Overlay overlay = new();
    private DateTimeOffset now = Start;
    private ForegroundProcess? front;

    public InGameBadgeServiceTests()
    {
        game = Path.Combine(root, "steamapps", "common", "Game");
        Directory.CreateDirectory(Path.Combine(game, "Binaries"));
        store = new UpscalerStateStore(Path.Combine(root, "state.json"));
        store.SetInstall("100", new InstalledUpscaler { Build = "fsr-4.1.2-beta", Engine = "optiscaler", Target = game }, 1);
    }

    public void Dispose() => Directory.Delete(root, true);

    private InGameBadgeService Service() => new(
        store,
        Data,
        () => new Dictionary<string, string> { ["100"] = game },
        overlay,
        () => front,
        new InGameFactsReader(_ => true, "anr"),
        () => now,
        new InGameText("en"));

    private void Log(string text) => File.WriteAllText(Path.Combine(game, "OptiScaler.log"), text);

    private void InFront(string image, int processId = 10) => front = new ForegroundProcess(new IntPtr(77), processId, image);

    [Fact]
    public void ShowsTheBadgeForSixSecondsOnceTheLogHasSomethingToSay()
    {
        var service = Service();
        InFront(Path.Combine(game, "Binaries", "Game.exe"));

        service.Tick();
        Assert.Null(overlay.Last);

        Log("[12:00:00.000] Creating new FSR 4.0.2 upscaler\n[12:00:00.000] Render Resolution: 1280x720, Display Resolution 2560x1440\n");
        now = Start.AddSeconds(3);
        service.Tick();
        var frame = Assert.IsType<OverlayFrame>(overlay.Last);
        Assert.Equal(new IntPtr(77), frame.GameWindow);
        Assert.Equal(
            new[] { UpscalerLabel.Badge(Data.Catalog.Build("fsr-4.1.2-beta"), null)!, "720p → 1440p" },
            frame.Lines[0].Spans.Select(span => span.Text));

        now = Start.AddSeconds(9.5);
        service.Tick();
        Assert.Null(overlay.Last);
    }

    [Fact]
    public void HidesWhenTheGameIsNotInFrontOrNotOurs()
    {
        Log("[12:00:00.000] Creating new FSR 4.0.2 upscaler\n");
        var service = Service();

        InFront(Path.Combine(game, "Game.exe"));
        service.Tick();
        Assert.NotNull(overlay.Last);

        InFront(Path.Combine(root, "elsewhere", "Browser.exe"), 11);
        service.Tick();
        Assert.Null(overlay.Last);

        front = null;
        service.Tick();
        Assert.Null(overlay.Last);
    }

    [Fact]
    public void AlwaysKeepsItUpAndOffNeverReadsAnything()
    {
        Log("[12:00:00.000] Creating new FSR 4.0.2 upscaler\n");
        var service = Service();
        InFront(Path.Combine(game, "Game.exe"));
        store.SetInGameMode(InGameModes.Always);

        service.Tick();
        now = Start.AddMinutes(10);
        service.Tick();
        Assert.NotNull(overlay.Last);

        store.SetInGameMode(InGameModes.Off);
        var reads = overlay.Presented;
        service.Tick();
        Assert.Null(overlay.Last);
        Assert.Equal(reads + 1, overlay.Presented);
    }

    [Fact]
    public void ReadsTheFactsAgainOnlyEveryTwoSeconds()
    {
        var service = Service();
        InFront(Path.Combine(game, "Game.exe"));
        store.SetInGameMode(InGameModes.Always);
        service.Tick();
        Assert.Null(overlay.Last);

        Log("[12:00:00.000] Creating new FSR 4.0.2 upscaler\n");
        now = Start.AddSeconds(1);
        service.Tick();
        Assert.Null(overlay.Last);

        now = Start.AddSeconds(2);
        service.Tick();
        Assert.NotNull(overlay.Last);
    }

    [Fact]
    public void FactsCarryFrameGenerationAndAFallbackFromTheLog()
    {
        Log("[12:00:00.000] Creating new FSR 3.1 upscaler\n[12:00:01.000] D3D12_Configure Enabled: true, result: 0\n");
        var stored = new StoredUpscaler(
            new InstalledUpscaler
            {
                Build = "fsr-4.1.2-beta",
                Engine = "optiscaler",
                Target = game,
                Options = new UpscalerChoice { FrameGen = true, FrameGenRoute = "optiscaler" },
            },
            1);

        var facts = new InGameFactsReader(_ => true, "anr").Read(stored, Data.Catalog.Build("fsr-4.1.2-beta"), Start)!;

        Assert.True(facts.Active);
        Assert.True(facts.Generating);
        Assert.Equal("FSR 3.1", facts.Fallback!.Observed);
        Assert.Null(new InGameFactsReader(_ => false, "anr").Read(stored, null, Start));
    }

    private sealed class Overlay : IInGameOverlay
    {
        public OverlayFrame? Last { get; private set; }

        public int Presented { get; private set; }

        public void Present(OverlayFrame? frame)
        {
            Last = frame;
            Presented++;
        }
    }
}
