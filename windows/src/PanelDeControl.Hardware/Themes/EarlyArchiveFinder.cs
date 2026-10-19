using System.Security.Cryptography;
using Microsoft.Win32;

namespace PanelDeControl.Hardware.Themes;

public sealed record EarlyArchive(string Path, ThemeEarlyRelease Release, ThemeEarlyArtifact Artifact);

/// <summary>
/// Finds published early archives in the user's Downloads folder (and one level below it), so a
/// zip saved from the early post installs with one button. Only files whose exact size appears in
/// <c>early.json</c> are hashed, and a hash is reused while the file is unchanged.
/// </summary>
public sealed class EarlyArchiveFinder
{
    private const int MaximumFiles = 400;

    private readonly Func<IEnumerable<string>> folders;
    private readonly Dictionary<string, (long Length, DateTime Written, string Sha256)> hashes = new(StringComparer.OrdinalIgnoreCase);
    private readonly object gate = new();

    public EarlyArchiveFinder(Func<IEnumerable<string>>? folders = null)
    {
        this.folders = folders ?? DefaultFolders;
    }

    public IReadOnlyList<EarlyArchive> Find(IReadOnlyList<ThemeEarlyRelease> releases)
    {
        var sizes = releases.SelectMany(release => release.Artifacts).Select(artifact => artifact.Size).ToHashSet();
        if (sizes.Count == 0)
        {
            return Array.Empty<EarlyArchive>();
        }

        var found = new List<EarlyArchive>();
        lock (gate)
        {
            foreach (var file in Candidates())
            {
                try
                {
                    var info = new FileInfo(file);
                    if (!sizes.Contains(info.Length) || info.Attributes.HasFlag(FileAttributes.ReparsePoint))
                    {
                        continue;
                    }

                    var sha = Hash(info);
                    foreach (var release in releases)
                    {
                        var artifact = release.Artifacts.FirstOrDefault(candidate => candidate.Size == info.Length && candidate.Sha256 == sha);
                        if (artifact is not null)
                        {
                            found.Add(new EarlyArchive(info.FullName, release, artifact));
                        }
                    }
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                }
            }
        }

        return found;
    }

    public static byte[] ReadVerified(EarlyArchive archive)
    {
        var bytes = File.ReadAllBytes(archive.Path);
        if (bytes.LongLength != archive.Artifact.Size || Sha(bytes) != archive.Artifact.Sha256)
        {
            throw new ThemeInstallException("artifact_hash_mismatch", "The early archive changed after it was found");
        }

        return bytes;
    }

    private IEnumerable<string> Candidates()
    {
        var count = 0;
        foreach (var folder in folders().Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            IEnumerable<string> files;
            try
            {
                files = Directory.EnumerateFiles(folder, "*.zip")
                    .Concat(Directory.EnumerateDirectories(folder).SelectMany(sub => SafeFiles(sub)));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            foreach (var file in files)
            {
                if (++count > MaximumFiles)
                {
                    yield break;
                }

                yield return file;
            }
        }
    }

    private static IEnumerable<string> SafeFiles(string folder)
    {
        try
        {
            return Directory.EnumerateFiles(folder, "*.zip").ToArray();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
    }

    private string Hash(FileInfo info)
    {
        if (hashes.TryGetValue(info.FullName, out var cached) && cached.Length == info.Length && cached.Written == info.LastWriteTimeUtc)
        {
            return cached.Sha256;
        }

        using var stream = info.OpenRead();
        var sha = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        hashes[info.FullName] = (info.Length, info.LastWriteTimeUtc, sha);
        return sha;
    }

    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static IEnumerable<string> DefaultFolders()
    {
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (OperatingSystem.IsWindows())
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders");
            if (key?.GetValue("{374DE290-123F-4565-9164-39C4925E467B}") is string downloads)
            {
                yield return downloads;
            }
        }

        yield return Path.Combine(profile, "Downloads");
        yield return Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
    }
}
