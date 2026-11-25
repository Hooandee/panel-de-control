using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>A refusal while reading something the user brought; <see cref="Code"/> is the Linux code without its <c>mod_</c> or <c>user_file_</c> prefix.</summary>
public sealed class UserSourceException : Exception
{
    public UserSourceException(string code)
        : base(code)
    {
        Code = code;
    }

    public string Code { get; }
}

public sealed class ArchiveEntry
{
    public ArchiveEntry(string name, long size)
    {
        Name = name;
        Size = size;
    }

    public string Name { get; }

    public long Size { get; }
}

public sealed class ArchiveListing
{
    public ArchiveListing(IReadOnlyList<ArchiveEntry> entries, bool encrypted)
    {
        Entries = entries;
        Encrypted = encrypted;
    }

    public IReadOnlyList<ArchiveEntry> Entries { get; }

    public bool Encrypted { get; }
}

/// <summary>Reads the archives a user brings. Nothing inside is ever run; links are refused.</summary>
public interface IUserArchive
{
    /// <summary>Every file with its size, read before anything is extracted.</summary>
    /// <exception cref="UserSourceException"><c>unreadable</c>, <c>unsafe_archive</c>, <c>password</c>, <c>password_wrong</c>, <c>password_unsupported</c>.</exception>
    ArchiveListing List(string path, string? password);

    /// <param name="wanted">Where each file goes under <paramref name="destination"/> ('/' separated) and the archive member it comes from.</param>
    void Extract(string path, IReadOnlyList<KeyValuePair<string, string>> wanted, string destination, string? password);
}

/// <summary>Files a recipe needs that only the user can download, as <c>user_deps.py</c> judges them.</summary>
public static class UserFiles
{
    public static readonly string[] Archives = { ".zip", ".7z", ".rar" };
    public const long MaximumArchive = 512L * 1024 * 1024;
    public const long MaximumMember = 256L * 1024 * 1024;
    public const int MaximumScanned = 200;
    public const int MaximumCandidates = 5;

    private static readonly Regex Nexus = new(@"-\d+-(\d+(?:-\d+){1,3})-\d{1,12}\.[A-Za-z0-9]+$", RegexOptions.CultureInvariant);
    private static readonly Regex Dotted = new(@"(?<![\d.])v?(\d+\.\d+(?:\.\d+){0,2})(?![\d.])", RegexOptions.CultureInvariant);

    public static string? FilenameVersion(string name)
    {
        var nexus = Nexus.Match(name);
        if (nexus.Success)
        {
            return nexus.Groups[1].Value.Replace('-', '.');
        }

        var dotted = Dotted.Match(name);
        return dotted.Success ? dotted.Groups[1].Value : null;
    }

    /// <summary>The first three parts of the DLL's FileVersion or ProductVersion.</summary>
    public static string? DllVersion(IReadOnlyDictionary<string, string> versionStrings)
    {
        foreach (var key in new[] { "FileVersion", "ProductVersion" })
        {
            if (!versionStrings.TryGetValue(key, out var value))
            {
                continue;
            }

            var found = Dotted.Match(value.Replace(',', '.').Replace(" ", ""));
            if (found.Success)
            {
                return string.Join(".", found.Groups[1].Value.Split('.').Take(3));
            }
        }

        return null;
    }

    /// <summary>Member names reach an archiver's command line: none may escape the folder, name a drive or read as an option.</summary>
    public static bool Unsafe(string member)
    {
        var normalized = member.Replace('\\', '/');
        return member.StartsWith("/", StringComparison.Ordinal) || member.StartsWith("\\", StringComparison.Ordinal) || member.Contains(':')
            || normalized.Split('/').Any(part => part == ".." || part.StartsWith("-", StringComparison.Ordinal));
    }

    /// <summary>The wanted file names and the archive member that carries each, or the reason this file is not what the dependency asks for.</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> Locate(RecipeDependency dependency, string fileName, Func<IReadOnlyList<string>> members)
    {
        var wanted = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var member in dependency.Files.Values)
        {
            wanted[Fold(member)] = member;
        }

        if (fileName.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
        {
            if (wanted.Count != 1 || !wanted.ContainsKey(Fold(fileName)))
            {
                throw new UserSourceException("missing_files");
            }

            return new[] { new KeyValuePair<string, string>(wanted[Fold(fileName)], fileName) };
        }

        var list = members();
        if (list.Any(Unsafe))
        {
            throw new UserSourceException("unsafe_archive");
        }

        var found = new List<KeyValuePair<string, string>>();
        foreach (var member in list)
        {
            var name = member.Replace('\\', '/').Split('/').Last(part => part.Length > 0);
            if (wanted.TryGetValue(Fold(name), out var destination))
            {
                if (found.Any(pair => pair.Key == destination))
                {
                    throw new UserSourceException("ambiguous_files");
                }

                found.Add(new KeyValuePair<string, string>(destination, member));
            }
        }

        if (found.Count != wanted.Count)
        {
            throw new UserSourceException("missing_files");
        }

        return found;
    }

    /// <summary><c>avoid</c>, <c>other_version</c> or <c>ready</c>.</summary>
    public static string State(RecipeDependency dependency, string? version)
    {
        if (version is not null && dependency.AvoidVersions.Contains(version))
        {
            return "avoid";
        }

        return version is not null && dependency.Version is not null && version != dependency.Version ? "other_version" : "ready";
    }

    internal static string Fold(string text) => text.ToLowerInvariant();

    /// <summary>A symbolic link or junction; a OneDrive placeholder is a plain file that downloads when read.</summary>
    public static bool IsLink(string path)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            return (attributes & FileAttributes.ReparsePoint) != 0
                && (attributes & (FileAttributes.Offline | (FileAttributes)0x00040000 | (FileAttributes)0x00400000)) == 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }
}

public sealed class UserFileStatus
{
    public string Id { get; set; } = "";

    public string? InstalledVersion { get; set; }

    public string? Filename { get; set; }

    /// <summary><c>missing</c>, <c>ready</c>, <c>other_version</c> or <c>avoid</c>.</summary>
    public string State { get; set; } = "missing";
}

/// <summary>The user's chosen file for each dependency, kept under <c>root/&lt;dependency id&gt;</c> so reinstalling never asks again.</summary>
public sealed class UserFileStore
{
    private static readonly UTF8Encoding Utf8 = new(false);
    private readonly string _root;
    private readonly IUserArchive _archive;
    private readonly Func<double> _clock;

    public UserFileStore(string root, IUserArchive archive, Func<double>? clock = null)
    {
        _root = root;
        _archive = archive;
        _clock = clock ?? (() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0);
    }

    public string Root => _root;

    private string Folder(RecipeDependency dependency) => Path.Combine(_root, dependency.Id);

    private DataObject Meta(RecipeDependency dependency)
    {
        try
        {
            return DataValue.Parse(File.ReadAllText(Path.Combine(Folder(dependency), "meta.json"), Utf8)) as DataObject
                ?? new DataObject(Array.Empty<KeyValuePair<string, DataValue>>());
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or DataFormatException)
        {
            return new DataObject(Array.Empty<KeyValuePair<string, DataValue>>());
        }
    }

    public UserFileStatus Status(RecipeDependency dependency)
    {
        var meta = Meta(dependency);
        var ready = meta.Count > 0 && dependency.Files.Values.All(member => File.Exists(Path.Combine(Folder(dependency), "files", member)));
        if (!ready)
        {
            return new UserFileStatus { Id = dependency.Id };
        }

        var version = (meta.Get("version") as DataString)?.Value;
        return new UserFileStatus
        {
            Id = dependency.Id,
            InstalledVersion = version,
            Filename = (meta.Get("filename") as DataString)?.Value,
            State = UserFiles.State(dependency, version),
        };
    }

    /// <summary>Destination beside the exe and the stored copy, or none while the user has not picked the file.</summary>
    public IReadOnlyDictionary<string, string> Sources(RecipeDependency dependency)
    {
        if (Status(dependency).State == "missing")
        {
            return new Dictionary<string, string>(StringComparer.Ordinal);
        }

        var files = Path.Combine(Folder(dependency), "files");
        return dependency.Files.ToDictionary(pair => pair.Key, pair => Path.Combine(files, pair.Value), StringComparer.Ordinal);
    }

    /// <summary>What the file carries, without keeping it.</summary>
    public UserFileInspection Inspect(RecipeDependency dependency, string path)
    {
        var name = Path.GetFileName(path);
        try
        {
            var located = Readable(dependency, path);
            var scratch = Path.Combine(_root, ".inspect-" + Guid.NewGuid().ToString("N"));
            try
            {
                var dlls = located.Where(pair => pair.Key.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)).ToList();
                if (dlls.Count > 0)
                {
                    Extract(path, dlls, scratch);
                }

                return new UserFileInspection(true, null, Version(dependency, path, scratch), name);
            }
            finally
            {
                DeleteQuietly(scratch);
            }
        }
        catch (UserSourceException error)
        {
            return new UserFileInspection(false, error.Code, null, name);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidDataException or ArgumentException)
        {
            return new UserFileInspection(false, "unreadable", null, name);
        }
    }

    public UserFileStatus Adopt(RecipeDependency dependency, string path)
    {
        Directory.CreateDirectory(_root);
        var staging = Path.Combine(_root, "." + dependency.Id + "-" + Guid.NewGuid().ToString("N"));
        try
        {
            var located = Readable(dependency, path);
            Extract(path, located, Path.Combine(staging, "files"));
            var version = Version(dependency, path, Path.Combine(staging, "files"));
            File.WriteAllText(Path.Combine(staging, "meta.json"), PythonJson.Write(new DataObject(new[]
            {
                new KeyValuePair<string, DataValue>("filename", new DataString(Path.GetFileName(path))),
                new KeyValuePair<string, DataValue>("version", version is null ? DataNull.Instance : new DataString(version)),
                new KeyValuePair<string, DataValue>("at", new DataNumber(null, _clock())),
            })), Utf8);
            Swap(staging, Folder(dependency));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidDataException or ArgumentException)
        {
            throw new UserSourceException("unreadable");
        }
        finally
        {
            DeleteQuietly(staging);
        }

        return Status(dependency);
    }

    public UserFileStatus Remove(RecipeDependency dependency)
    {
        DeleteQuietly(Folder(dependency));
        return Status(dependency);
    }

    private IReadOnlyList<KeyValuePair<string, string>> Readable(RecipeDependency dependency, string path)
    {
        var info = new FileInfo(path);
        var extension = Path.GetExtension(path).ToLowerInvariant();
        if (!info.Exists || !UserFiles.Archives.Concat(new[] { ".dll" }).Contains(extension) || UserFiles.IsLink(path))
        {
            throw new UserSourceException("unreadable");
        }

        if (info.Length > UserFiles.MaximumArchive)
        {
            throw new UserSourceException("too_large");
        }

        return UserFiles.Locate(dependency, info.Name, () => _archive.List(path, null).Entries.Select(entry => entry.Name).ToList());
    }

    private void Extract(string path, IReadOnlyList<KeyValuePair<string, string>> located, string destination)
    {
        Directory.CreateDirectory(destination);
        if (path.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
        {
            File.Copy(path, Path.Combine(destination, located[0].Key), false);
            return;
        }

        var listing = _archive.List(path, null).Entries.ToDictionary(entry => entry.Name, entry => entry.Size, StringComparer.Ordinal);
        if (located.Any(pair => listing.TryGetValue(pair.Value, out var size) && size > UserFiles.MaximumMember))
        {
            throw new UserSourceException("too_large");
        }

        _archive.Extract(path, located, destination, null);
        foreach (var pair in located)
        {
            var file = new FileInfo(Path.Combine(destination, pair.Key.Replace('/', Path.DirectorySeparatorChar)));
            if (!file.Exists || file.Length > UserFiles.MaximumMember)
            {
                throw new UserSourceException(file.Exists ? "too_large" : "unreadable");
            }
        }
    }

    private static string? Version(RecipeDependency dependency, string path, string extracted)
    {
        foreach (var member in dependency.Files.Values)
        {
            var file = Path.Combine(extracted, member);
            if (member.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) && File.Exists(file))
            {
                using var stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read);
                if (UserFiles.DllVersion(PeImage.VersionStrings(stream)) is { } version)
                {
                    return version;
                }
            }
        }

        return UserFiles.FilenameVersion(Path.GetFileName(path));
    }

    internal static void Swap(string staging, string destination)
    {
        string? trash = null;
        if (Directory.Exists(destination))
        {
            trash = destination + ".old-" + Guid.NewGuid().ToString("N");
            Directory.Move(destination, trash);
        }

        Directory.Move(staging, destination);
        if (trash is not null)
        {
            DeleteQuietly(trash);
        }
    }

    public static void DeleteQuietly(string folder)
    {
        try
        {
            if (Directory.Exists(folder))
            {
                foreach (var file in Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories))
                {
                    File.SetAttributes(file, FileAttributes.Normal);
                }

                Directory.Delete(folder, true);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
    }
}

public sealed class UserFileInspection
{
    public UserFileInspection(bool ok, string? reason, string? version, string filename)
    {
        Ok = ok;
        Reason = reason;
        Version = version;
        Filename = filename;
    }

    public bool Ok { get; }

    public string? Reason { get; }

    public string? Version { get; }

    public string Filename { get; }
}
