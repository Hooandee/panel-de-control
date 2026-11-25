using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class GameAudioPolicyTests : IDisposable
{
    private readonly string directory = Path.Combine(Path.GetTempPath(), "pdc-game-audio-" + Guid.NewGuid().ToString("N"));

    private string StatePath => Path.Combine(directory, "game-audio-silenced.json");

    public void Dispose()
    {
        if (Directory.Exists(directory))
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void SilencesOnlyTheGameAndGivesItsSoundBack()
    {
        var policy = new GameAudioPolicy(StatePath);
        var sessions = new[]
        {
            new AudioSessionState(10, "witcher3.exe", false),
            new AudioSessionState(20, "steamwebhelper.exe", false),
            new AudioSessionState(30, "spotify.exe", false),
        };

        Assert.Equal(new bool?[] { true, null, null }, policy.Decide(true, sessions, pid => pid == 10));
        Assert.True(policy.HasOwed);

        var silenced = new[] { sessions[0] with { Muted = true }, sessions[1], sessions[2] };
        Assert.Equal(new bool?[] { null, null, null }, policy.Decide(true, silenced, pid => pid == 10));
        Assert.Equal(new bool?[] { false, null, null }, policy.Decide(false, silenced, pid => pid == 10));
        Assert.False(policy.HasOwed);
        Assert.False(File.Exists(StatePath));
    }

    [Fact]
    public void LeavesAGameThePlayerMutedAlone()
    {
        var policy = new GameAudioPolicy(StatePath);
        var muted = new[] { new AudioSessionState(10, "game.exe", true) };

        Assert.Equal(new bool?[] { null }, policy.Decide(true, muted, _ => true));
        Assert.Equal(new bool?[] { null }, policy.Decide(false, muted, _ => true));
        Assert.False(policy.HasOwed);
    }

    [Fact]
    public void RemembersAGameClosedWhileSilencedAcrossRestarts()
    {
        var first = new GameAudioPolicy(StatePath);
        first.Decide(true, new[] { new AudioSessionState(10, "game.exe", false) }, _ => true);
        Assert.Equal(new bool?[0], first.Decide(false, Array.Empty<AudioSessionState>(), _ => true));
        Assert.True(first.HasOwed);

        // Windows kept the mute for the executable: its next run starts silent and gets its sound back.
        var restarted = new GameAudioPolicy(StatePath);
        Assert.True(restarted.HasOwed);
        Assert.Equal(new bool?[] { false }, restarted.Decide(false, new[] { new AudioSessionState(77, "GAME.exe", true) }, _ => true));
        Assert.False(restarted.HasOwed);
    }

    [Fact]
    public void GamesAreWhatSteamStartsButNotSteamItself()
    {
        var processes = new Dictionary<int, ProcessEntry>
        {
            [1] = new(0, "explorer.exe"),
            [2] = new(1, "steam.exe"),
            [3] = new(2, "steamwebhelper.exe"),
            [4] = new(2, "launcher.exe"),
            [5] = new(4, "game.exe"),
            [6] = new(1, "spotify.exe"),
            [7] = new(7, "loop.exe"),
        };

        Assert.True(SteamGameProcesses.IsGame(processes, 5));
        Assert.True(SteamGameProcesses.IsGame(processes, 4));
        Assert.False(SteamGameProcesses.IsGame(processes, 3));
        Assert.False(SteamGameProcesses.IsGame(processes, 2));
        Assert.False(SteamGameProcesses.IsGame(processes, 6));
        Assert.False(SteamGameProcesses.IsGame(processes, 7));
        Assert.False(SteamGameProcesses.IsGame(processes, 99));
    }
}
