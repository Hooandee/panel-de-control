namespace PanelDeControl.Core.FileSystem;

/// <summary>The real disk behind <see cref="IReadOnlyFileSystem"/>: read-only, never throws, follows links except where asked.</summary>
public sealed class PhysicalFileSystem : IReadOnlyFileSystem
{
    public static readonly PhysicalFileSystem Instance = new();

    private PhysicalFileSystem()
    {
    }

    public IReadOnlyList<FileSystemEntry> List(string directory)
    {
        try
        {
            return new DirectoryInfo(directory).EnumerateFileSystemInfos()
                .Select(info => new FileSystemEntry(info.Name, PointsToDirectory(info), IsLink(info)))
                .ToList();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException or ArgumentException)
        {
            return Array.Empty<FileSystemEntry>();
        }
    }

    public bool IsFile(string path) => File.Exists(path);

    public bool IsDirectory(string path) => Directory.Exists(path);

    public bool Exists(string path) => File.Exists(path) || Directory.Exists(path);

    public bool IsSymbolicLink(string path)
    {
        try
        {
            var info = new FileInfo(path);
            return (info.Exists || Directory.Exists(path)) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException or ArgumentException or NotSupportedException)
        {
            return false;
        }
    }

    public long? Length(string path)
    {
        try
        {
            var info = new FileInfo(path);
            return info.Exists ? info.Length : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException or ArgumentException or NotSupportedException)
        {
            return null;
        }
    }

    public Stream? OpenRead(string path)
    {
        try
        {
            // A running game or Steam may hold the file open; reading must never block or fail them.
            return new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException or ArgumentException or NotSupportedException)
        {
            return null;
        }
    }

    private static bool IsLink(FileSystemInfo info) => (info.Attributes & FileAttributes.ReparsePoint) != 0;

    private static bool PointsToDirectory(FileSystemInfo info) =>
        info is DirectoryInfo || ((info.Attributes & FileAttributes.Directory) != 0) || (IsLink(info) && Directory.Exists(info.FullName));
}
