using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Steam;

public enum SteamUpdateState
{
    /// <summary>Steam is downloading or applying an update.</summary>
    Running = 0,

    /// <summary>Steam has an update queued or the install is otherwise incomplete.</summary>
    Pending = 1,
}

/// <summary>A game Steam installed, read from its library's appmanifest.</summary>
public sealed class SteamApp
{
    public SteamApp(string appId, string name, string root, long stateFlags, string? buildId)
    {
        AppId = appId;
        Name = name;
        Root = root;
        StateFlags = stateFlags;
        BuildId = buildId;
    }

    public string AppId { get; }

    public string Name { get; }

    /// <summary>The game folder under <c>steamapps/common</c>.</summary>
    public string Root { get; }

    public long StateFlags { get; }

    public string? BuildId { get; }

    public SteamUpdateState? UpdateState => SteamLibrary.UpdateState(StateFlags);
}

/// <summary>Steam libraries and the games installed in them.</summary>
public static class SteamLibrary
{
    public const long StateFullyInstalled = 4;

    /// <summary>StateFlags bits for an update being downloaded (256) or staged (1024).</summary>
    public const long StateUpdateRunning = 256 | 1024;

    /// <summary>
    /// Each Steam root plus every library its libraryfolders.vdf lists, in that order, keeping those with a
    /// <c>steamapps</c> folder. Windows paths differ in case and separators only, so those count as the same library.
    /// </summary>
    public static IReadOnlyList<string> LibraryPaths(IReadOnlyFileSystem fileSystem, IEnumerable<string> steamRoots)
    {
        var libraries = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var root in steamRoots)
        {
            var candidates = new List<string> { root };
            var folders = ValveTextVdf.TryRead(fileSystem, FileSystemPath.Join(root, "steamapps/libraryfolders.vdf"))?.GetObject("libraryfolders");
            if (folders is not null)
            {
                candidates.AddRange(folders.Entries
                    .Select(entry => (entry.Value as VdfObject)?.GetString("path"))
                    .Where(path => path is not null)
                    .Cast<string>());
            }

            foreach (var path in candidates)
            {
                if (fileSystem.IsDirectory(FileSystemPath.Join(path, "steamapps")) && seen.Add(SameLibraryKey(path)))
                {
                    libraries.Add(path);
                }
            }
        }

        return libraries;
    }

    public static SteamApp? FindInstalled(IReadOnlyFileSystem fileSystem, IEnumerable<string> libraries, string appId)
    {
        if (!PythonText.IsDecimal(appId))
        {
            return null;
        }

        foreach (var library in libraries)
        {
            var state = ValveTextVdf.TryRead(fileSystem, FileSystemPath.Join(library, $"steamapps/appmanifest_{appId}.acf"))?.GetObject("appstate");
            if (state is null)
            {
                continue;
            }

            var installDir = state.GetString("installdir");
            if (string.IsNullOrEmpty(installDir) || installDir!.Contains('/'))
            {
                continue;
            }

            var root = FileSystemPath.Join(library, "steamapps/common/" + installDir);
            if (!fileSystem.IsDirectory(root))
            {
                continue;
            }

            var flags = state.GetString("stateflags") is { } text && PythonText.TryParseInteger(text, out var parsed) ? parsed : 0;
            var buildId = state.GetString("buildid") is { } build && PythonText.IsDecimal(build) ? build : null;
            var name = state.GetString("name") is { Length: > 0 } title ? title : appId;
            return new SteamApp(appId, name, root, flags, buildId);
        }

        return null;
    }

    /// <summary>Null when Steam has nothing pending for the game.</summary>
    public static SteamUpdateState? UpdateState(long flags)
    {
        if (flags == StateFullyInstalled)
        {
            return null;
        }

        return (flags & StateUpdateRunning) != 0 ? SteamUpdateState.Running : SteamUpdateState.Pending;
    }

    private static string SameLibraryKey(string path) => path.Replace('\\', '/').TrimEnd('/');
}
