using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

/// <summary>Suspends and resumes whole processes; a process is told apart from a later one with its id by its start.</summary>
public interface IGameProcessSuspender
{
    /// <summary>When the process started (FILETIME ticks), or null when it is gone or cannot be read.</summary>
    long? StartTicks(int processId);

    bool Suspend(int processId);

    bool Resume(int processId);
}

public sealed record FrozenProcess(int ProcessId, long StartTicks, string Executable);

/// <summary>
/// Which of Steam's game processes are frozen while a theme's menus are over the game (games.pause, as Linux's
/// game_freeze.py), and giving each one back. Only processes Steam started that are not Steam's own freeze
/// (<see cref="SteamGameProcesses"/>), each once, so each resumes once. Every process frozen here is written to disk
/// until it runs again: a companion that stops while a game is frozen thaws it the next time it starts, and a process
/// whose id now belongs to another start is left alone.
/// </summary>
public sealed class GameFreezePolicy
{
    private readonly string statePath;
    private readonly IGameProcessSuspender suspender;
    private readonly List<FrozenProcess> frozen;

    public GameFreezePolicy(string statePath, IGameProcessSuspender suspender)
    {
        this.statePath = statePath;
        this.suspender = suspender;
        frozen = Load(statePath);
    }

    public bool HasFrozen => frozen.Count > 0;

    public IReadOnlyList<FrozenProcess> Frozen => frozen;

    /// <summary>Freezes the game processes not frozen yet (a game can start more while frozen); the ones it froze.</summary>
    public IReadOnlyList<FrozenProcess> Freeze(IReadOnlyDictionary<int, ProcessEntry> processes)
    {
        var added = new List<FrozenProcess>();
        foreach (var (processId, entry) in processes)
        {
            if (frozen.Any(process => process.ProcessId == processId) || !SteamGameProcesses.IsGame(processes, processId))
            {
                continue;
            }

            if (suspender.StartTicks(processId) is not { } start || !suspender.Suspend(processId))
            {
                continue;
            }

            var process = new FrozenProcess(processId, start, entry.Executable);
            frozen.Add(process);
            added.Add(process);
        }

        if (added.Count > 0)
        {
            Save();
        }

        return added;
    }

    /// <summary>Resumes every process frozen here that still runs as the same process; the ones it resumed.</summary>
    public IReadOnlyList<FrozenProcess> Thaw()
    {
        var resumed = new List<FrozenProcess>();
        foreach (var process in frozen)
        {
            if (suspender.StartTicks(process.ProcessId) == process.StartTicks && suspender.Resume(process.ProcessId))
            {
                resumed.Add(process);
            }
        }

        frozen.Clear();
        Save();
        return resumed;
    }

    private static List<FrozenProcess> Load(string path)
    {
        try
        {
            var stored = JsonSerializer.Deserialize<FrozenProcess[]>(File.ReadAllText(path)) ?? Array.Empty<FrozenProcess>();
            return stored.Where(process => process is not null && process.ProcessId > 0).ToList();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return new List<FrozenProcess>();
        }
    }

    private void Save()
    {
        try
        {
            if (frozen.Count == 0)
            {
                File.Delete(statePath);
                return;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(statePath)!);
            var temporary = statePath + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(frozen));
            File.Move(temporary, statePath, overwrite: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            CompanionLog.Write("themes.game_freeze_state", exception);
        }
    }
}
