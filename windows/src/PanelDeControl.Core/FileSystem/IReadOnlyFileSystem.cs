namespace PanelDeControl.Core.FileSystem;

/// <summary>
/// The disk as game detection sees it. Paths are absolute; Core joins segments with '/', which Windows
/// accepts. Every query follows symbolic links except <see cref="IsSymbolicLink"/>, and none throws for a
/// missing or unreadable path.
/// </summary>
public interface IReadOnlyFileSystem
{
    /// <summary>The folder's entries, or none when it is missing or cannot be read.</summary>
    IReadOnlyList<FileSystemEntry> List(string directory);

    bool IsFile(string path);

    bool IsDirectory(string path);

    bool Exists(string path);

    bool IsSymbolicLink(string path);

    /// <summary>Size in bytes, or null when the file cannot be read.</summary>
    long? Length(string path);

    /// <summary>A readable, seekable stream, or null when the file cannot be opened.</summary>
    Stream? OpenRead(string path);
}

public sealed class FileSystemEntry
{
    public FileSystemEntry(string name, bool isDirectory, bool isSymbolicLink)
    {
        Name = name;
        IsDirectory = isDirectory;
        IsSymbolicLink = isSymbolicLink;
    }

    public string Name { get; }

    /// <summary>A folder, or a link to one.</summary>
    public bool IsDirectory { get; }

    public bool IsSymbolicLink { get; }
}

internal static class FileSystemPath
{
    public static string Join(string directory, string relative)
    {
        if (relative.Length == 0)
        {
            return directory;
        }

        return directory.EndsWith("/", StringComparison.Ordinal) || directory.EndsWith("\\", StringComparison.Ordinal)
            ? directory + relative
            : directory + "/" + relative;
    }

    /// <summary>The folder part of a '/'-separated relative path, empty for a top-level name.</summary>
    public static string RelativeParent(string relative)
    {
        var slash = relative.LastIndexOf('/');
        return slash < 0 ? string.Empty : relative.Substring(0, slash);
    }

    public static byte[]? ReadAtMost(IReadOnlyFileSystem fileSystem, string path, int limit)
    {
        try
        {
            using var stream = fileSystem.OpenRead(path);
            if (stream is null)
            {
                return null;
            }

            var chunk = new byte[64 * 1024];
            using var collected = new MemoryStream();
            while (collected.Length < limit)
            {
                var read = stream.Read(chunk, 0, (int)Math.Min(chunk.Length, limit - collected.Length));
                if (read == 0)
                {
                    break;
                }

                collected.Write(chunk, 0, read);
            }

            return collected.ToArray();
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }
}
