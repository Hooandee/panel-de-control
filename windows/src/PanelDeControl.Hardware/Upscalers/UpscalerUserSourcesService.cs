using System.Runtime.InteropServices;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// What the user brings: a mod for one game (<c>add_mod</c>) and the files a recipe asks the user to download
/// (<c>add_user_file</c>), as Linux's <c>mod_candidates</c> … <c>remove_user_file</c> do. Panel keeps a copy under its state
/// folder and the next install places it; the game manifest owns the files so removal restores the game.
/// </summary>
public sealed partial class UpscalerService
{
    private UserModStore userMods = null!;
    private UserFileStore userFiles = null!;
    private Func<IReadOnlyList<string>> downloadFolders = null!;
    private string profile = "";

    private void InitializeUserSources(IUserArchive? archive, Func<IReadOnlyList<string>>? folders, string? profileFolder)
    {
        archive ??= UserArchive.Locate(Path.Combine(Environment.SystemDirectory, "tar.exe"));
        userMods = new UserModStore(Path.Combine(StateFolder, "user-mods"), archive);
        userFiles = new UserFileStore(Path.Combine(StateFolder, "user-files"), archive, clock);
        profile = profileFolder ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        downloadFolders = folders ?? (() => new[] { KnownFolders.Downloads(), Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory) }
            .Where(folder => !string.IsNullOrEmpty(folder)).Distinct(StringComparer.OrdinalIgnoreCase).ToList());
    }

    private (string Folder, IReadOnlyList<string> All) Folders()
    {
        var all = downloadFolders();
        return (all.FirstOrDefault(Directory.Exists) ?? profile, all);
    }

    private UpscalersResponse ModCandidates()
    {
        var (folder, all) = Folders();
        var downloading = UserMods.Downloading(all, DateTime.UtcNow);
        return Ok(candidates: new UpscalerCandidates
        {
            Folder = folder,
            Candidates = UserMods.Candidates(all).Select(item => new UpscalerCandidate { Path = item.Path, Filename = item.Filename, Size = item.Size }).ToArray(),
            Downloading = downloading is null ? null : new UpscalerDownloading { Filename = downloading.Filename, Size = downloading.Size },
        });
    }

    private UpscalersResponse AddMod(string appId, string path, string? password)
    {
        if (password is { Length: > UpscalersRequest.MaximumPasswordLength })
        {
            throw new UpscalerException("mod_password_wrong");
        }

        var chosen = Chosen(path, "mod_unreadable");
        string relative;
        IReadOnlyList<string> existing;
        IReadOnlyList<string> rootFolders;
        lock (settingsLock)
        {
            EnsureNoJob(null);
            (relative, existing, rootFolders) = ModPlan(appId);
        }

        PreparedUserMod prepared;
        try
        {
            prepared = userMods.Prepare(appId, chosen, relative, existing, rootFolders, password);
        }
        catch (UserSourceException error)
        {
            throw new UpscalerException("mod_" + error.Code);
        }

        try
        {
            lock (settingsLock)
            {
                EnsureNoJob(null);
                if (ModPlan(appId).Relative != relative)
                {
                    throw new UpscalerException("mod_moved");
                }

                try
                {
                    userMods.Commit(prepared, StampNanoseconds);
                }
                catch (UserSourceException error)
                {
                    throw new UpscalerException("mod_" + error.Code);
                }
            }
        }
        finally
        {
            userMods.Discard(prepared);
        }

        return Ok(game: Game(appId));
    }

    private (string Relative, IReadOnlyList<string> Existing, IReadOnlyList<string> RootFolders) ModPlan(string appId)
    {
        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        var analysis = Analyze(app, Resolved(app, "optiscaler")?.Exe);
        var target = analysis.Target is { } found ? Path.GetFullPath(found) : throw new UpscalerException("no_exe");
        var relative = Path.GetRelativePath(app.Root, target).Replace(Path.DirectorySeparatorChar, '/');
        return (relative == "." ? "" : relative,
            fileSystem.List(target).Select(entry => entry.Name).ToList(),
            fileSystem.List(app.Root).Where(entry => entry.IsDirectory).Select(entry => entry.Name).ToList());
    }

    private UpscalersResponse RemoveMod(string appId)
    {
        lock (settingsLock)
        {
            EnsureNoJob(null);
            try
            {
                userMods.Remove(appId);
            }
            catch (UserSourceException error)
            {
                throw new UpscalerException("mod_" + error.Code);
            }
        }

        return Ok(game: Game(appId));
    }

    private UpscalersResponse UserFileCandidates(string dependencyId)
    {
        var dependency = UserDependency(dependencyId);
        var (folder, all) = Folders();
        var files = new List<(long Stamp, string Path)>();
        foreach (var entry in all)
        {
            try
            {
                if (UserFiles.NotPlain(Path.GetFullPath(entry)))
                {
                    continue;
                }

                foreach (var file in new DirectoryInfo(entry).EnumerateFiles())
                {
                    if (!UserFiles.IsLink(file.FullName)
                        && (UserFiles.Archives.Concat(new[] { ".dll" }).Any(extension => file.Name.EndsWith(extension, StringComparison.OrdinalIgnoreCase))))
                    {
                        files.Add((file.LastWriteTimeUtc.Ticks, file.FullName));
                    }
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
            {
            }
        }

        var found = new List<UpscalerCandidate>();
        foreach (var file in files.OrderByDescending(item => item.Stamp).ThenByDescending(item => item.Path, StringComparer.Ordinal).Take(UserFiles.MaximumScanned))
        {
            var checkedFile = InspectCached(dependency, file.Path);
            if (checkedFile.Ok)
            {
                found.Add(new UpscalerCandidate { Path = file.Path, Filename = Path.GetFileName(file.Path), Version = checkedFile.Version });
                if (found.Count >= UserFiles.MaximumCandidates)
                {
                    break;
                }
            }
        }

        return Ok(candidates: new UpscalerCandidates { Folder = folder, Candidates = found.ToArray() });
    }

    private UpscalersResponse AddUserFile(string appId, string dependencyId, string path)
    {
        var dependency = UserDependency(dependencyId);
        var chosen = Chosen(path, "user_file_unreadable");
        lock (settingsLock)
        {
            EnsureNoJob(null);
        }

        PreparedUserFile prepared;
        try
        {
            prepared = userFiles.Prepare(dependency, chosen);
        }
        catch (UserSourceException error)
        {
            throw new UpscalerException(error.Code is "missing_files" or "ambiguous_files" ? "user_file_wrong" : "user_file_unreadable");
        }

        try
        {
            lock (settingsLock)
            {
                EnsureNoJob(null);
                try
                {
                    userFiles.Commit(prepared);
                }
                catch (UserSourceException)
                {
                    throw new UpscalerException("user_file_unreadable");
                }
            }
        }
        finally
        {
            userFiles.Discard(prepared);
        }

        return Ok(game: Game(appId));
    }

    private UpscalersResponse RemoveUserFile(string appId, string dependencyId)
    {
        var dependency = UserDependency(dependencyId);
        lock (settingsLock)
        {
            EnsureNoJob(null);
            userFiles.Remove(dependency);
        }

        return Ok(game: Game(appId));
    }

    private RecipeDependency UserDependency(string id) =>
        data.Recipes is { } catalog && catalog.Dependencies.TryGetValue(id, out var dependency) && dependency.Kind == "user_files"
            ? dependency
            : throw new UpscalerException("unknown_dependency");

    private readonly Dictionary<string, (long Stamp, long Length, UserFileInspection Result)> inspected = new(StringComparer.Ordinal);

    /// <summary>The download watcher asks again every few seconds: a file is looked at once per version.</summary>
    private UserFileInspection InspectCached(RecipeDependency dependency, string path)
    {
        FileInfo info;
        try
        {
            info = new FileInfo(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return userFiles.Inspect(dependency, path);
        }

        var key = dependency.Id + "|" + path;
        lock (inspected)
        {
            if (inspected.TryGetValue(key, out var known) && known.Stamp == info.LastWriteTimeUtc.Ticks && known.Length == info.Length)
            {
                return known.Result;
            }
        }

        var result = userFiles.Inspect(dependency, path);
        lock (inspected)
        {
            if (inspected.Count > 512)
            {
                inspected.Clear();
            }

            inspected[key] = (info.LastWriteTimeUtc.Ticks, info.Length, result);
        }

        return result;
    }

    /// <summary>
    /// The picked file as a plain path Panel may read: under the user's profile, the download folders, or on another drive
    /// (the removable-media case of Linux), never through a link and never a network path or mapped network drive.
    /// </summary>
    private string Chosen(string path, string code)
    {
        string full;
        try
        {
            full = Path.GetFullPath(path);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            throw new UpscalerException(code);
        }

        if (!File.Exists(full) || UserFiles.NotPlain(full))
        {
            throw new UpscalerException(code);
        }

        var root = Path.GetPathRoot(full) ?? "";

        var systemRoot = Path.GetPathRoot(Environment.SystemDirectory) ?? "";
        var allowed = IsInside(full, profile) || downloadFolders().Any(folder => folder.Length > 0 && IsInside(full, folder))
            || !string.Equals(root, systemRoot, StringComparison.OrdinalIgnoreCase);
        return allowed ? full : throw new UpscalerException(code);
    }

    private long StampNanoseconds() => (long)(clock() * 1_000_000_000d);

    private UpscalerModStatus? ModStatus(string appId, InstalledUpscaler? install)
    {
        var status = userMods.Status(appId);
        if (status is null)
        {
            return install?.Mod is { } removed
                ? new UpscalerModStatus { Filename = removed.Key, Count = 0, Files = Array.Empty<string>(), Applied = false, Removed = true }
                : null;
        }

        return new UpscalerModStatus
        {
            Filename = status.Filename,
            Count = status.Count,
            Files = status.Files.ToArray(),
            Applied = install?.Mod is { } applied && applied.Value == status.Id,
        };
    }

    private UserModInstall? ModFor(SteamApp app)
    {
        var status = userMods.Status(app.AppId);
        return status is null
            ? null
            : new UserModInstall
            {
                Filename = status.Filename ?? "",
                Id = status.Id ?? "",
                Target = status.Target ?? "",
                GameRoot = app.Root,
                Sources = userMods.Sources(app.AppId),
            };
    }

    private static class KnownFolders
    {
        private static readonly Guid DownloadsId = new("374DE290-123F-4565-9164-39C4925E467B");

        /// <summary>The Downloads folder as the shell reports it, which may have been moved to another drive.</summary>
        public static string Downloads()
        {
            try
            {
                var id = DownloadsId;
                if (SHGetKnownFolderPath(ref id, 0, IntPtr.Zero, out var path) == 0 && path != IntPtr.Zero)
                {
                    try
                    {
                        return Marshal.PtrToStringUni(path) ?? "";
                    }
                    finally
                    {
                        Marshal.FreeCoTaskMem(path);
                    }
                }
            }
            catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
            {
            }

            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
        }

        [DllImport("shell32.dll")]
        private static extern int SHGetKnownFolderPath(ref Guid id, uint flags, IntPtr token, out IntPtr path);
    }
}
