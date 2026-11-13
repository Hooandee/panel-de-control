using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// A disk for fixtures; links point at files only. By default it is case-sensitive like the Linux backend's;
/// <c>windows</c> makes it ignore case and accept '\\' as a separator.
/// </summary>
internal sealed class InMemoryFileSystem : IReadOnlyFileSystem
{
    private readonly bool windows;
    private readonly Dictionary<string, (byte[] Content, long Size)> files;
    private readonly HashSet<string> directories;
    private readonly Dictionary<string, string> links;

    public InMemoryFileSystem(bool windows = false)
    {
        this.windows = windows;
        var comparer = windows ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal;
        files = new Dictionary<string, (byte[] Content, long Size)>(comparer);
        directories = new HashSet<string>(comparer);
        links = new Dictionary<string, string>(comparer);
    }

    public void AddFile(string path, byte[] content, long? size = null)
    {
        path = Normal(path);
        AddParents(path);
        files[path] = (content, Math.Max(size ?? 0, content.Length));
    }

    public void AddDirectory(string path)
    {
        path = Normal(path);
        AddParents(path);
        directories.Add(path);
    }

    public void AddLink(string path, string target)
    {
        path = Normal(path);
        AddParents(path);
        links[path] = Normal(target);
    }

    public IReadOnlyList<FileSystemEntry> List(string directory)
    {
        if (!IsDirectory(directory))
        {
            return Array.Empty<FileSystemEntry>();
        }

        var prefix = Normal(directory).TrimEnd('/') + "/";
        var comparison = windows ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return files.Keys.Concat(directories).Concat(links.Keys)
            .Where(path => path.StartsWith(prefix, comparison) && path.IndexOf('/', prefix.Length) < 0)
            .Distinct(StringComparer.Ordinal)
            .Select(path => new FileSystemEntry(path.Substring(prefix.Length), IsDirectory(path), links.ContainsKey(path)))
            .ToArray();
    }

    public bool IsFile(string path) => files.ContainsKey(Resolve(path));

    public bool IsDirectory(string path) => directories.Contains(Resolve(path).TrimEnd('/'));

    public bool Exists(string path) => IsFile(path) || IsDirectory(path);

    public bool IsSymbolicLink(string path) => links.ContainsKey(Normal(path));

    public long? Length(string path) => files.TryGetValue(Resolve(path), out var file) ? file.Size : null;

    public Stream? OpenRead(string path)
    {
        if (!files.TryGetValue(Resolve(path), out var file))
        {
            return null;
        }

        var data = new byte[file.Size];
        Array.Copy(file.Content, data, file.Content.Length);
        return new MemoryStream(data, writable: false);
    }

    private string Normal(string path) => windows ? path.Replace('\\', '/') : path;

    private string Resolve(string path)
    {
        var normal = Normal(path);
        return links.TryGetValue(normal, out var target) ? target : normal;
    }

    private void AddParents(string path)
    {
        var slash = path.LastIndexOf('/');
        while (slash > 0)
        {
            directories.Add(path.Substring(0, slash));
            slash = path.LastIndexOf('/', slash - 1);
        }
    }
}
