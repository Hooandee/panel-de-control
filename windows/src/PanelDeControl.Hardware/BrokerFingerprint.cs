using System.Security.Cryptography;
using System.Text;

namespace PanelDeControl.Hardware;

/// <summary>
/// One hash for every file of the companion folder. The package is unsigned, so its identity alone can
/// be copied; the elevated installer records this hash and the service only trusts a companion whose
/// folder still hashes the same. The apphost alone would not do: it loads whatever DLL sits next to it.
/// </summary>
public static class BrokerFingerprint
{
    public static string Compute(string directory)
    {
        var lines = new StringBuilder();
        foreach (var file in Files(directory))
        {
            using var stream = new FileStream(file.FullName, FileMode.Open, FileAccess.Read, FileShare.Read);
            lines.Append(Relative(directory, file)).Append('\t')
                .Append(Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()).Append('\n');
        }

        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(lines.ToString()))).ToLowerInvariant();
    }

    /// <summary>Changes whenever a file is added, removed, resized or rewritten; cheap enough per connection.</summary>
    public static string Shape(string directory)
    {
        var shape = new StringBuilder();
        foreach (var file in Files(directory))
        {
            shape.Append(Relative(directory, file)).Append('\t')
                .Append(file.Length).Append('\t')
                .Append(file.LastWriteTimeUtc.Ticks).Append('\n');
        }

        return shape.ToString();
    }

    private static IEnumerable<FileInfo> Files(string directory) =>
        new DirectoryInfo(directory)
            .EnumerateFiles("*", SearchOption.AllDirectories)
            .OrderBy(file => Relative(directory, file), StringComparer.Ordinal);

    private static string Relative(string directory, FileInfo file) =>
        Path.GetRelativePath(directory, file.FullName).Replace('\\', '/').ToLowerInvariant();
}
