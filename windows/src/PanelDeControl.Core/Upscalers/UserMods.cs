using System.Text;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

public sealed class UserModStatus
{
    public string? Filename { get; set; }

    public string? Id { get; set; }

    public string? Target { get; set; }

    public int Count { get; set; }

    public IReadOnlyList<string> Files { get; set; } = Array.Empty<string>();
}

public sealed class DownloadCandidate
{
    public DownloadCandidate(string path, string filename, long size)
    {
        Path = path;
        Filename = filename;
        Size = size;
    }

    public string Path { get; }

    public string Filename { get; }

    public long Size { get; }
}

public sealed class DownloadInProgress
{
    public DownloadInProgress(string filename, long size)
    {
        Filename = filename;
        Size = size;
    }

    public string Filename { get; }

    public long Size { get; }
}

/// <summary>
/// A mod the user brings for one game, as <c>user_mods.py</c> handles it: Panel keeps a copy and installs its files beside
/// the game's exe together with OptiScaler, through the same manifest, so turning the upscaler off takes them out.
/// </summary>
public static class UserMods
{
    public const int MaximumFiles = 400;
    public const long MaximumTotal = 2L * 1024 * 1024 * 1024;
    public const int Preview = 8;
    public const int CandidateLimit = 6;

    /// <summary>Where to get the mod a game's wiki entry asks for, when it is a free download.</summary>
    public static readonly IReadOnlyDictionary<string, string> Downloads = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["1245620"] = "https://www.patreon.com/huutaiii/posts/erss-fg-free-v4-125972766",
    };

    private static readonly string[] OptiScalerFiles =
    {
        "optiscaler.ini", "optiscaler.dll", "optiscaler.log", "optiscaler/*", "nvngx.dll", "nvngx_dlss.dll", "libxess*.dll",
        "amd_fidelityfx_*.dll", "amdxcffx64.dll", "fakenvapi*", "nvapi64.dll", "dlssg_to_fsr3*", "d3d12_optiscaler/*",
    };

    private static readonly string[] Partial = { ".crdownload", ".part", ".download", ".tmp" };

    private static readonly string[] Reserved = { "con", "prn", "aux", "nul" };

    /// <summary>The members split like <c>PurePosixPath(member.replace("\\", "/")).parts</c>.</summary>
    internal static string[] Parts(string member)
    {
        var normalized = member.Replace('\\', '/');
        var parts = new List<string>();
        if (normalized.StartsWith("/", StringComparison.Ordinal))
        {
            parts.Add("/");
        }

        parts.AddRange(normalized.Split('/').Where(part => part.Length > 0 && part != "."));
        return parts.ToArray();
    }

    /// <summary>
    /// Where each archive member goes, relative to the exe's folder (<paramref name="target"/>, relative to the game root).
    /// A single wrapping folder the game does not have is dropped, then the game's own path down to the exe's folder; a mod that
    /// also reaches another folder of the game root cannot be laid out beside the exe and is refused.
    /// </summary>
    public static IReadOnlyList<KeyValuePair<string, string>> Layout(IReadOnlyList<string> members, string target, IEnumerable<string>? existing = null,
        IEnumerable<string>? rootDirs = null)
    {
        var present = new HashSet<string>((existing ?? Array.Empty<string>()).Select(UserFiles.Fold), StringComparer.Ordinal);
        var roots = new HashSet<string>((rootDirs ?? Array.Empty<string>()).Select(UserFiles.Fold), StringComparer.Ordinal);
        var paths = members.Select(Parts).ToList();
        if (paths.Count == 0)
        {
            throw new UserSourceException("empty");
        }

        var prefix = Parts(target).Select(UserFiles.Fold).ToArray();
        if (paths.All(path => path.Length > 1) && paths.Select(path => UserFiles.Fold(path[0])).Distinct().Count() == 1
            && !present.Contains(UserFiles.Fold(paths[0][0])) && !roots.Contains(UserFiles.Fold(paths[0][0])))
        {
            paths = paths.Select(path => path.Skip(1).ToArray()).ToList();
        }

        if (prefix.Length > 0 && paths.All(path => path.Length > prefix.Length && path.Take(prefix.Length).Select(UserFiles.Fold).SequenceEqual(prefix)))
        {
            paths = paths.Select(path => path.Skip(prefix.Length).ToArray()).ToList();
        }
        else if (paths.Any(path => path.Length > 1 && roots.Contains(UserFiles.Fold(path[0])) && !present.Contains(UserFiles.Fold(path[0]))))
        {
            throw new UserSourceException("layout");
        }

        var result = new List<KeyValuePair<string, string>>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        for (var index = 0; index < members.Count; index++)
        {
            var destination = string.Join("/", paths[index]);
            if (!seen.Add(UserFiles.Fold(destination)))
            {
                throw new UserSourceException("ambiguous_files");
            }

            result.Add(new KeyValuePair<string, string>(destination, members[index]));
        }

        return result;
    }

    /// <summary>Whether a mod file would replace one Panel's OptiScaler installs.</summary>
    public static bool ReplacesOptiScaler(IEnumerable<string> destinations) =>
        destinations.Any(destination => OptiScalerFiles.Any(pattern => Matches(UserFiles.Fold(destination), pattern)));

    private static bool Matches(string text, string pattern)
    {
        // fnmatch: '*' crosses '/', and the patterns here have no other wildcard.
        var pieces = pattern.Split('*');
        if (pieces.Length == 1)
        {
            return text == pattern;
        }

        if (!text.StartsWith(pieces[0], StringComparison.Ordinal) || !text.EndsWith(pieces[pieces.Length - 1], StringComparison.Ordinal)
            || text.Length < pieces[0].Length + pieces[pieces.Length - 1].Length)
        {
            return false;
        }

        var position = pieces[0].Length;
        var limit = text.Length - pieces[pieces.Length - 1].Length;
        for (var index = 1; index < pieces.Length - 1; index++)
        {
            var found = text.IndexOf(pieces[index], position, StringComparison.Ordinal);
            if (found < 0 || found + pieces[index].Length > limit)
            {
                return false;
            }

            position = found + pieces[index].Length;
        }

        return position <= limit;
    }

    /// <summary>A name Windows would not create as the archive means it.</summary>
    public static bool InvalidOnWindows(string member) =>
        Parts(member).Any(part => part != "/" && (part.EndsWith(".", StringComparison.Ordinal) || part.EndsWith(" ", StringComparison.Ordinal)
            || part.IndexOfAny(new[] { '<', '>', '"', '|', '?', '*' }) >= 0 || part.Any(char.IsControl)
            || Reserved.Contains(UserFiles.Fold(part.Split('.')[0])) || IsNumberedDevice(UserFiles.Fold(part.Split('.')[0]))));

    private static bool IsNumberedDevice(string stem) =>
        stem.Length == 4 && (stem.StartsWith("com", StringComparison.Ordinal) || stem.StartsWith("lpt", StringComparison.Ordinal)) && stem[3] is >= '1' and <= '9';

    /// <summary>Archives in the folders, newest first. A mod has no fixed content to check, so the user picks it.</summary>
    public static IReadOnlyList<DownloadCandidate> Candidates(IEnumerable<string> folders, int limit = CandidateLimit)
    {
        var found = new List<(long Stamp, string Path, long Size)>();
        foreach (var folder in folders)
        {
            try
            {
                foreach (var entry in new DirectoryInfo(folder).EnumerateFiles())
                {
                    if (UserFiles.IsLink(entry.FullName) || !UserFiles.Archives.Any(extension => entry.Name.EndsWith(extension, StringComparison.OrdinalIgnoreCase)))
                    {
                        continue;
                    }

                    found.Add((entry.LastWriteTimeUtc.Ticks, entry.FullName, entry.Length));
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }

        return found.OrderByDescending(item => item.Stamp).ThenByDescending(item => item.Path, StringComparer.Ordinal).Take(limit)
            .Select(item => new DownloadCandidate(item.Path, System.IO.Path.GetFileName(item.Path), item.Size)).ToList();
    }

    /// <summary>The download still being written, newest first.</summary>
    public static DownloadInProgress? Downloading(IEnumerable<string> folders, DateTime now)
    {
        var found = new List<(long Stamp, string Name, long Size)>();
        foreach (var folder in folders)
        {
            try
            {
                foreach (var entry in new DirectoryInfo(folder).EnumerateFiles())
                {
                    if (!UserFiles.IsLink(entry.FullName) && Partial.Any(extension => entry.Name.EndsWith(extension, StringComparison.OrdinalIgnoreCase))
                        && (now - entry.LastWriteTimeUtc).TotalSeconds < 60)
                    {
                        found.Add((entry.LastWriteTimeUtc.Ticks, entry.Name, entry.Length));
                    }
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }

        if (found.Count == 0)
        {
            return null;
        }

        var newest = found.OrderByDescending(item => item.Stamp).ThenByDescending(item => item.Name, StringComparer.Ordinal).First();
        return new DownloadInProgress(newest.Name, newest.Size);
    }
}

/// <summary>One mod per game, kept under <c>root/&lt;appid&gt;</c> so a reinstall or a new upscaler version never asks again.</summary>
public sealed class UserModStore
{
    private static readonly UTF8Encoding Utf8 = new(false);
    private readonly string _root;
    private readonly IUserArchive _archive;

    public UserModStore(string root, IUserArchive archive)
    {
        _root = root;
        _archive = archive;
    }

    public string Root => _root;

    private string Folder(string appId)
    {
        if (appId.Length == 0 || !appId.All(char.IsLetterOrDigit))
        {
            throw new UserSourceException("unreadable");
        }

        return Path.Combine(_root, appId);
    }

    private DataObject? Meta(string appId)
    {
        try
        {
            return DataValue.Parse(File.ReadAllText(Path.Combine(Folder(appId), "meta.json"), Utf8)) is DataObject { } meta && meta.Get("files") is DataArray ? meta : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or DataFormatException)
        {
            return null;
        }
    }

    public UserModStatus? Status(string appId)
    {
        var meta = Meta(appId);
        var files = DataValue.StringItems(meta?.Get("files"));
        if (meta is null || files.Count == 0 || !files.All(file => File.Exists(Path.Combine(Folder(appId), "files", file.Replace('/', Path.DirectorySeparatorChar)))))
        {
            return null;
        }

        return new UserModStatus
        {
            Filename = (meta.Get("filename") as DataString)?.Value,
            Id = (meta.Get("id") as DataString)?.Value,
            Target = (meta.Get("target") as DataString)?.Value,
            Count = files.Count,
            Files = files.Take(UserMods.Preview).ToList(),
        };
    }

    /// <summary>Destination beside the exe and the stored copy; empty without a mod.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> Sources(string appId)
    {
        if (Status(appId) is null)
        {
            return Array.Empty<KeyValuePair<string, string>>();
        }

        var folder = Path.Combine(Folder(appId), "files");
        return DataValue.StringItems(Meta(appId)!.Get("files"))
            .Select(name => new KeyValuePair<string, string>(name, Path.Combine(folder, name.Replace('/', Path.DirectorySeparatorChar)))).ToList();
    }

    public UserModStatus Adopt(string appId, string path, string target, IEnumerable<string> existing, IEnumerable<string> rootDirs, string? password, Func<long> stamp)
    {
        var folder = Folder(appId);
        var wanted = UserMods.Layout(Readable(path, password), target, existing, rootDirs);
        if (UserMods.ReplacesOptiScaler(wanted.Select(pair => pair.Key)))
        {
            throw new UserSourceException("conflict");
        }

        Directory.CreateDirectory(_root);
        var staging = Path.Combine(_root, "." + appId + "-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(staging);
            _archive.Extract(path, wanted, Path.Combine(staging, "files"), password);
            foreach (var pair in wanted)
            {
                if (!File.Exists(Path.Combine(staging, "files", pair.Key.Replace('/', Path.DirectorySeparatorChar))))
                {
                    throw new UserSourceException("unsafe_archive");
                }
            }

            File.WriteAllText(Path.Combine(staging, "meta.json"), PythonJson.Write(new DataObject(new[]
            {
                new KeyValuePair<string, DataValue>("filename", new DataString(Path.GetFileName(path))),
                new KeyValuePair<string, DataValue>("files", new DataArray(wanted.Select(pair => pair.Key).OrderBy(name => name, StringComparer.Ordinal)
                    .Select(name => (DataValue)new DataString(name)).ToList())),
                new KeyValuePair<string, DataValue>("target", new DataString(target)),
                new KeyValuePair<string, DataValue>("id", new DataString(Path.GetFileName(path) + "@" + stamp().ToString(System.Globalization.CultureInfo.InvariantCulture))),
            })), Utf8);
            UserFileStore.Swap(staging, folder);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidDataException or ArgumentException)
        {
            throw new UserSourceException("unreadable");
        }
        finally
        {
            UserFileStore.DeleteQuietly(staging);
        }

        return Status(appId) ?? new UserModStatus();
    }

    public void Remove(string appId) => UserFileStore.DeleteQuietly(Folder(appId));

    private IReadOnlyList<string> Readable(string path, string? password)
    {
        var info = new FileInfo(path);
        if (!info.Exists || UserFiles.IsLink(path) || !UserFiles.Archives.Contains(Path.GetExtension(path).ToLowerInvariant()))
        {
            throw new UserSourceException("unreadable");
        }

        if (info.Length > UserFiles.MaximumArchive)
        {
            throw new UserSourceException("too_large");
        }

        ArchiveListing listing;
        try
        {
            listing = _archive.List(path, password);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            throw new UserSourceException("unreadable");
        }

        var members = listing.Entries.Select(entry => entry.Name).ToList();
        if (members.Any(member => UserFiles.Unsafe(member) || UserMods.InvalidOnWindows(member)))
        {
            throw new UserSourceException("unsafe_archive");
        }

        if (members.Count > UserMods.MaximumFiles)
        {
            throw new UserSourceException("too_many_files");
        }

        if (listing.Entries.Any(entry => entry.Size > UserFiles.MaximumMember) || listing.Entries.Sum(entry => entry.Size) > UserMods.MaximumTotal)
        {
            throw new UserSourceException("too_large");
        }

        if (listing.Encrypted && string.IsNullOrEmpty(password))
        {
            throw new UserSourceException("password");
        }

        return members;
    }
}
