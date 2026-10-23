using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;

namespace PanelDeControl.Hardware.Themes;

public sealed class ThemeInstallException : Exception
{
    public ThemeInstallException(string code, string message)
        : base(message)
    {
        Code = code;
    }

    public string Code { get; }
}

/// <summary>
/// Verifies a published theme archive and swaps it into the theme library atomically. A failed
/// install leaves the previous version exactly as it was.
/// </summary>
public sealed class ThemePackageInstaller
{
    public const int MaximumFiles = 2_048;
    public const long MaximumUncompressedBytes = 64L * 1024 * 1024;
    public const int MaximumCompressionRatio = 200;
    public const int MaximumPathBytes = 512;

    private const int UnixFileTypeMask = 0xF000;
    private const int UnixRegularFile = 0x8000;

    private readonly string libraryRoot;

    public ThemePackageInstaller(string libraryRoot)
    {
        this.libraryRoot = libraryRoot;
    }

    public InstalledTheme Install(ThemeRelease release, byte[] archive)
    {
        if (archive.LongLength != release.Artifact.Size)
        {
            throw new ThemeInstallException("artifact_size_mismatch", "Downloaded size does not match the catalog");
        }

        if (Convert.ToHexString(SHA256.HashData(archive)).ToLowerInvariant() != release.Artifact.Sha256)
        {
            throw new ThemeInstallException("artifact_hash_mismatch", "Downloaded hash does not match the catalog");
        }

        Directory.CreateDirectory(libraryRoot);
        var transaction = Path.Combine(libraryRoot, $".install-{Guid.NewGuid():N}");
        var staged = Path.Combine(transaction, release.CssLoaderName);
        var destination = Path.Combine(libraryRoot, release.CssLoaderName);
        var backup = Path.Combine(transaction, ".previous");
        try
        {
            Extract(archive, release.CssLoaderName, staged);
            var theme = ThemeLibrary.Load(staged)
                ?? throw new ThemeInstallException("invalid_package", "Package is not a theme");
            Validate(release, theme, staged);

            var hadPrevious = Directory.Exists(destination);
            if (hadPrevious)
            {
                Directory.Move(destination, backup);
            }

            try
            {
                Directory.Move(staged, destination);
            }
            catch
            {
                if (hadPrevious)
                {
                    Directory.Move(backup, destination);
                }

                throw;
            }

            return theme with { Directory = destination };
        }
        catch (ThemeManifestException exception)
        {
            throw new ThemeInstallException("invalid_package", exception.Message);
        }
        catch (InvalidDataException exception)
        {
            throw new ThemeInstallException("invalid_archive", exception.Message);
        }
        finally
        {
            TryDelete(transaction);
        }
    }

    public static void RecoverInterruptedInstalls(string libraryRoot)
    {
        if (!Directory.Exists(libraryRoot))
        {
            return;
        }

        foreach (var transaction in Directory.EnumerateDirectories(libraryRoot, ".install-*"))
        {
            var backup = Path.Combine(transaction, ".previous");
            if (Directory.Exists(backup))
            {
                var theme = ThemeLibrary.Load(backup);
                var destination = theme is null ? null : Path.Combine(libraryRoot, theme.Name);
                if (destination is not null && !Directory.Exists(destination))
                {
                    Directory.Move(backup, destination);
                }
            }

            TryDelete(transaction);
        }
    }

    private static void Extract(byte[] archive, string rootName, string staged)
    {
        using var zip = new ZipArchive(new MemoryStream(archive, writable: false), ZipArchiveMode.Read);
        if (zip.Entries.Count == 0 || zip.Entries.Count > MaximumFiles)
        {
            throw new ThemeInstallException("unsafe_archive", "Archive file count is out of bounds");
        }

        long total = 0;
        foreach (var entry in zip.Entries)
        {
            var path = entry.FullName;
            if (Encoding.UTF8.GetByteCount(path) > MaximumPathBytes)
            {
                throw new ThemeInstallException("unsafe_archive", "Archive path is too long");
            }

            var isDirectory = path.EndsWith('/');
            var relative = path.TrimEnd('/');
            var separator = relative.IndexOf('/');
            var root = separator < 0 ? relative : relative[..separator];
            if (root != rootName || !ThemeManifest.IsSafeRelativePath(relative))
            {
                throw new ThemeInstallException("unsafe_archive", $"Archive entry {path} is outside the theme root");
            }

            var unixType = (entry.ExternalAttributes >> 16) & UnixFileTypeMask;
            if (!isDirectory && unixType != 0 && unixType != UnixRegularFile)
            {
                throw new ThemeInstallException("unsafe_archive", "Archive contains links or devices");
            }

            if (isDirectory || separator < 0)
            {
                continue;
            }

            total += entry.Length;
            if (total > MaximumUncompressedBytes
                || (entry.CompressedLength > 0 && entry.Length / entry.CompressedLength > MaximumCompressionRatio))
            {
                throw new ThemeInstallException("unsafe_archive", "Archive expands beyond its limits");
            }

            var target = Path.Combine(staged, relative[(separator + 1)..].Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            using var input = entry.Open();
            using var output = File.Create(target);
            CopyBounded(input, output, entry.Length);
        }
    }

    private static void CopyBounded(Stream input, Stream output, long declaredLength)
    {
        var buffer = new byte[81920];
        long written = 0;
        int read;
        while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
        {
            written += read;
            if (written > declaredLength)
            {
                throw new ThemeInstallException("unsafe_archive", "Archive entry is larger than declared");
            }

            output.Write(buffer, 0, read);
        }
    }

    private static void Validate(ThemeRelease release, InstalledTheme theme, string staged)
    {
        if (theme.Name != release.CssLoaderName || theme.Manifest.Version != release.Version)
        {
            throw new ThemeInstallException("identity_mismatch", "Package identity does not match the catalog");
        }

        if (theme.Marker?.CatalogIdentity != release.CatalogId)
        {
            throw new ThemeInstallException("identity_mismatch", "Package marker does not match the catalog");
        }

        foreach (var file in theme.Manifest.AllCssFiles)
        {
            if (!File.Exists(Path.Combine(staged, file.Replace('/', Path.DirectorySeparatorChar))))
            {
                throw new ThemeInstallException("invalid_package", $"Declared stylesheet {file} is missing");
            }
        }
    }

    private static void TryDelete(string directory)
    {
        try
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, recursive: true);
            }
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
