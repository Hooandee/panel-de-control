using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class GameFreezePolicyTests : IDisposable
{
    private readonly string directory = Path.Combine(Path.GetTempPath(), "pdc-game-freeze-" + Guid.NewGuid().ToString("N"));

    private string StatePath => Path.Combine(directory, "game-frozen.json");

    public void Dispose()
    {
        if (Directory.Exists(directory))
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    // steam.exe (1) started the game (10, with a helper 11) and its own web helper (2); explorer (3) started notepad (30).
    private static Dictionary<int, ProcessEntry> Table() => new()
    {
        [1] = new ProcessEntry(0, "steam.exe"),
        [2] = new ProcessEntry(1, "steamwebhelper.exe"),
        [10] = new ProcessEntry(1, "SB-Win64-Shipping.exe"),
        [11] = new ProcessEntry(10, "CrashReportClient.exe"),
        [3] = new ProcessEntry(0, "explorer.exe"),
        [30] = new ProcessEntry(3, "notepad.exe"),
    };

    private sealed class FakeSuspender : IGameProcessSuspender
    {
        public Dictionary<int, long> Starts { get; } = new() { [1] = 100, [2] = 200, [10] = 1000, [11] = 1100, [3] = 300, [30] = 3000 };
        public Dictionary<int, int> Count { get; } = new();
        public HashSet<int> Refuse { get; } = new();

        public long? StartTicks(int processId) => Starts.TryGetValue(processId, out var start) ? start : null;

        public bool Suspend(int processId)
        {
            if (Refuse.Contains(processId) || !Starts.ContainsKey(processId))
            {
                return false;
            }

            Count[processId] = Count.GetValueOrDefault(processId) + 1;
            return true;
        }

        public bool Resume(int processId)
        {
            Count[processId] = Count.GetValueOrDefault(processId) - 1;
            return true;
        }
    }

    [Fact]
    public void FreezesOnlyTheGameOnceAndThawsIt()
    {
        var suspender = new FakeSuspender();
        var policy = new GameFreezePolicy(StatePath, suspender);

        var frozen = policy.Freeze(Table());
        Assert.Equal(new[] { 10, 11 }, frozen.Select(process => process.ProcessId).Order());
        Assert.Empty(policy.Freeze(Table()));
        Assert.Equal(1, suspender.Count[10]);
        Assert.False(suspender.Count.ContainsKey(1) || suspender.Count.ContainsKey(2) || suspender.Count.ContainsKey(30));
        Assert.True(File.Exists(StatePath));

        Assert.Equal(2, policy.Thaw().Count);
        Assert.Equal(0, suspender.Count[10]);
        Assert.Equal(0, suspender.Count[11]);
        Assert.False(policy.HasFrozen);
        Assert.False(File.Exists(StatePath));
    }

    [Fact]
    public void FreezesAProcessTheGameStartsWhileFrozen()
    {
        var suspender = new FakeSuspender();
        var policy = new GameFreezePolicy(StatePath, suspender);
        var table = Table();
        table.Remove(11);
        Assert.Single(policy.Freeze(table));
        Assert.Single(policy.Freeze(Table()));
        Assert.Equal(2, policy.Frozen.Count);
    }

    [Fact]
    public void AStoppedCompanionThawsWhatItLeftFrozenAndSparesAReusedId()
    {
        var suspender = new FakeSuspender();
        new GameFreezePolicy(StatePath, suspender).Freeze(Table());

        // The companion stopped; the helper exited and its id now belongs to another process.
        suspender.Starts[11] = 9999;
        var restarted = new GameFreezePolicy(StatePath, suspender);
        Assert.True(restarted.HasFrozen);
        var resumed = restarted.Thaw();
        Assert.Equal(new[] { 10 }, resumed.Select(process => process.ProcessId));
        Assert.Equal(0, suspender.Count[10]);
        Assert.Equal(1, suspender.Count[11]);
        Assert.False(File.Exists(StatePath));
    }

    [Fact]
    public void SkipsWhatItCannotSuspend()
    {
        var suspender = new FakeSuspender();
        suspender.Refuse.Add(10);
        var policy = new GameFreezePolicy(StatePath, suspender);
        Assert.Equal(new[] { 11 }, policy.Freeze(Table()).Select(process => process.ProcessId));
    }

    [Fact]
    public void ReadsABrokenStateFileAsNothingFrozen()
    {
        Directory.CreateDirectory(directory);
        File.WriteAllText(StatePath, "{not json");
        Assert.False(new GameFreezePolicy(StatePath, new FakeSuspender()).HasFrozen);
    }
}
