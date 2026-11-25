using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

public sealed record AudioSessionState(int ProcessId, string Executable, bool Muted);

/// <summary>
/// Which mixer sessions to mute while a theme silences the running game, and which to give back. Windows keeps a
/// per-app mute across runs, so a game closed while silenced would start silent next time: every executable muted
/// here is remembered on disk until one of its sessions has its sound back. A game the player muted is left alone.
/// </summary>
public sealed class GameAudioPolicy
{
    private readonly string statePath;
    private readonly HashSet<string> owed;

    public GameAudioPolicy(string statePath)
    {
        this.statePath = statePath;
        owed = Load(statePath);
    }

    public bool HasOwed => owed.Count > 0;

    /// <summary>The mute each session should get, or null to leave it as it is.</summary>
    public IReadOnlyList<bool?> Decide(bool silenced, IReadOnlyList<AudioSessionState> sessions, Func<int, bool> isGame)
    {
        var decisions = new bool?[sessions.Count];
        var changed = false;
        if (silenced)
        {
            for (var index = 0; index < sessions.Count; index++)
            {
                var session = sessions[index];
                if (session.Muted || !isGame(session.ProcessId))
                {
                    continue;
                }

                decisions[index] = true;
                changed |= owed.Add(session.Executable);
            }
        }
        else
        {
            var restored = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (var index = 0; index < sessions.Count; index++)
            {
                var session = sessions[index];
                if (!owed.Contains(session.Executable))
                {
                    continue;
                }

                if (session.Muted)
                {
                    decisions[index] = false;
                }

                restored.Add(session.Executable);
            }

            foreach (var executable in restored)
            {
                changed |= owed.Remove(executable);
            }
        }

        if (changed)
        {
            Save();
        }

        return decisions;
    }

    private static HashSet<string> Load(string path)
    {
        try
        {
            var names = JsonSerializer.Deserialize<string[]>(File.ReadAllText(path)) ?? Array.Empty<string>();
            return new HashSet<string>(names.Where(name => !string.IsNullOrWhiteSpace(name)), StringComparer.OrdinalIgnoreCase);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        }
    }

    private void Save()
    {
        try
        {
            if (owed.Count == 0)
            {
                File.Delete(statePath);
                return;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(statePath)!);
            var temporary = statePath + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(owed.Order(StringComparer.OrdinalIgnoreCase).ToArray()));
            File.Move(temporary, statePath, overwrite: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            CompanionLog.Write("themes.game_audio_state", exception);
        }
    }
}

public readonly record struct ProcessEntry(int ParentProcessId, string Executable);

/// <summary>Games are what Steam starts: processes below <c>steam.exe</c> that are not Steam's own.</summary>
public static class SteamGameProcesses
{
    private const int MaximumDepth = 32;

    private static readonly HashSet<string> SteamOwn = new(StringComparer.OrdinalIgnoreCase)
    {
        "steam.exe", "steamwebhelper.exe", "steamservice.exe", "steamerrorreporter.exe", "steamerrorreporter64.exe",
        "gameoverlayui.exe", "gameoverlayui64.exe", "steamsysinfo.exe",
    };

    public static bool IsGame(IReadOnlyDictionary<int, ProcessEntry> processes, int processId)
    {
        if (!processes.TryGetValue(processId, out var entry) || SteamOwn.Contains(entry.Executable))
        {
            return false;
        }

        var seen = new HashSet<int> { processId };
        for (var depth = 0; depth < MaximumDepth; depth++)
        {
            if (!seen.Add(entry.ParentProcessId) || !processes.TryGetValue(entry.ParentProcessId, out entry))
            {
                return false;
            }

            if (entry.Executable.Equals("steam.exe", StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }
}
