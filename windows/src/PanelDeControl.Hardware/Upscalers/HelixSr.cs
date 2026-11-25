using System.ComponentModel;
using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using PanelDeControl.Core.Data;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

public sealed class HelixProcessResult
{
    public HelixProcessResult(int exitCode, string standardOutput, string standardError)
    {
        ExitCode = exitCode;
        StandardOutput = standardOutput;
        StandardError = standardError;
    }

    public int ExitCode { get; }

    public string StandardOutput { get; }

    public string StandardError { get; }
}

/// <summary>Runs HelixSR's bridge; replaceable so a test needs no Python.</summary>
public interface IHelixProcess
{
    /// <summary>Throws <see cref="TimeoutException"/> after killing the process when it outlives <paramref name="timeout"/>.</summary>
    Task<HelixProcessResult> RunAsync(string executable, IReadOnlyList<string> arguments, string workingDirectory, TimeSpan timeout, CancellationToken cancel);
}

/// <summary>A child process without a shell: arguments are passed as they are and the output is read while it runs.</summary>
public sealed class HelixProcess : IHelixProcess
{
    private const int KeptCharacters = 1024 * 1024;

    public async Task<HelixProcessResult> RunAsync(string executable, IReadOnlyList<string> arguments, string workingDirectory, TimeSpan timeout, CancellationToken cancel)
    {
        var start = new ProcessStartInfo(executable)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false),
        };
        foreach (var argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        using var process = Process.Start(start) ?? throw new IOException("process did not start");
        process.StandardInput.Close();
        var output = Tail(process.StandardOutput);
        var errors = Tail(process.StandardError);
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancel);
        limit.CancelAfter(timeout);
        try
        {
            await process.WaitForExitAsync(limit.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            Kill(process);
            if (cancel.IsCancellationRequested)
            {
                throw;
            }

            throw new TimeoutException("bridge timed out");
        }

        try
        {
            await Task.WhenAll(output, errors).WaitAsync(limit.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            Kill(process);
            if (cancel.IsCancellationRequested)
            {
                throw;
            }

            throw new TimeoutException("bridge timed out");
        }

        return new HelixProcessResult(process.ExitCode, await output.ConfigureAwait(false), await errors.ConfigureAwait(false));
    }

    private static void Kill(Process process)
    {
        try
        {
            process.Kill(true);
        }
        catch (Exception exception) when (exception is InvalidOperationException or Win32Exception)
        {
        }
    }

    private static async Task<string> Tail(StreamReader reader)
    {
        var kept = new StringBuilder();
        var buffer = new char[8192];
        int read;
        while ((read = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) > 0)
        {
            kept.Append(buffer, 0, read);
            if (kept.Length > KeptCharacters)
            {
                kept.Remove(0, kept.Length - KeptCharacters);
            }
        }

        return kept.ToString();
    }
}

/// <summary>
/// HelixSR through its own bridge, as the Linux backend does (<c>helixsr.py</c>). HelixSR's licence forbids modifying or
/// redistributing its files, so Panel only unpacks the official release as it is and runs its JSON bridge with python.org's
/// own embeddable Python, the one HelixSR's Windows setup pins; both live in Panel's folder, never on the user's PATH.
/// </summary>
public sealed class HelixSr
{
    public const string PythonStage = "python";
    public const string UnpackStage = "unpack";
    public static readonly TimeSpan BridgeTimeout = TimeSpan.FromSeconds(180);

    private const string PythonExecutable = "python.exe";
    private const int RenameAttempts = 8;
    private static readonly TimeSpan RenameDelay = TimeSpan.FromMilliseconds(250);
    private readonly string releases;
    private readonly string python;
    private readonly string fallbackRelease;
    private readonly IHelixProcess process;
    private readonly TimeSpan timeout;

    /// <param name="root">The upscalers folder: releases go under <c>helixsr</c> and Python under <c>python</c>, physical paths a child process sees too.</param>
    /// <param name="fallbackRelease">The release folder name when none was recorded.</param>
    public HelixSr(string root, string fallbackRelease, IHelixProcess? process = null, TimeSpan? timeout = null)
    {
        releases = Path.Combine(root, "helixsr");
        python = Path.Combine(root, "python");
        this.fallbackRelease = fallbackRelease;
        this.process = process ?? new HelixProcess();
        this.timeout = timeout ?? BridgeTimeout;
    }

    /// <summary>HelixSR as the catalog pins it, in Panel's own folder.</summary>
    public static HelixSr ForCatalog(BuildCatalog catalog, string root, IHelixProcess? process = null) =>
        new(root, Path.GetFileNameWithoutExtension(catalog.Asset(catalog.Archives["helixsr"])!.FileName), process);

    internal Action<string, string>? MoveDirectory { get; set; }

    public string ReleasesFolder => releases;

    public string PythonFolder => python;

    public string Release
    {
        get
        {
            string name;
            try
            {
                name = File.ReadAllText(Path.Combine(releases, HelixRelease.Current)).Trim();
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                name = string.Empty;
            }

            return Path.Combine(releases, HelixRelease.IsReleaseName(name) ? name : fallbackRelease);
        }
    }

    public string ReleaseName => Path.GetFileName(Release);

    public bool ReleaseReady => File.Exists(Path.Combine(Release, HelixRelease.Complete)) && File.Exists(Path.Combine(Release, "setup", "helixsr_bridge.py"));

    public bool PythonReady => File.Exists(Path.Combine(python, PythonExecutable)) && File.Exists(Path.Combine(python, HelixRelease.Complete));

    /// <summary>Whether the bridge can run at all: the release and the Python that drives it are both here.</summary>
    public bool Ready => ReleaseReady && PythonReady;

    /// <summary>SHA-256 of the archive this release came from; null for one unpacked before Panel recorded it.</summary>
    public string? Digest
    {
        get
        {
            try
            {
                var value = File.ReadAllText(Path.Combine(Release, HelixRelease.Complete)).Trim();
                return HelixRelease.IsDigest(value) ? value : null;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                return null;
            }
        }
    }

    public bool PythonIs(string digest)
    {
        try
        {
            return File.ReadAllText(Path.Combine(python, HelixRelease.Complete)).Trim() == digest && File.Exists(Path.Combine(python, PythonExecutable));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    /// <summary>Unpacks python.org's embeddable package as it is.</summary>
    public void UnpackPython(string archive, string digest)
    {
        Unpack(archive, python, Relative, digest, PythonExecutable, "python.exe missing");
    }

    /// <summary>Unpacks only the release folder of HelixSR's official ZIP, as it is.</summary>
    public void UnpackRelease(string archive, string digest)
    {
        var name = HelixRelease.NameOf(archive, fallbackRelease);
        var destination = Path.Combine(releases, name);
        var previous = Release;
        Unpack(archive, destination, entry => HelixRelease.Destination(entry, name), digest, HelixRelease.Bridge, "bridge missing");
        try
        {
            File.WriteAllText(Path.Combine(releases, HelixRelease.Current), name, new UTF8Encoding(false));
            if (!string.Equals(previous, destination, StringComparison.OrdinalIgnoreCase) && Directory.Exists(previous)
                && string.Equals(Path.GetDirectoryName(previous), releases, StringComparison.OrdinalIgnoreCase))
            {
                DeleteTree(previous);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new UpscalerException("unpack_failed", exception.GetType().Name);
        }
    }

    public Task<HelixGame> InstallAsync(string game, CancellationToken cancel) =>
        BridgeAsync(cancel, "install", "--game", Path.GetFullPath(game), "--way", "fsr");

    public Task<HelixGame> RemoveAsync(string game, CancellationToken cancel) =>
        BridgeAsync(cancel, "remove", "--game", Path.GetFullPath(game));

    /// <summary>The marker that says a game's HelixSR is Panel's, beside the other Panel files of the folder.</summary>
    public static void WriteMarker(string target, string way, string release)
    {
        var meta = Path.Combine(target, GameManifest.Folder);
        if (Directory.Exists(meta) && (File.GetAttributes(meta) & FileAttributes.ReparsePoint) != 0)
        {
            throw new UpscalerException("unsafe_folder");
        }

        Directory.CreateDirectory(meta);
        var path = Path.Combine(meta, GameFiles.HelixMarker);
        var temporary = path + ".tmp";
        File.WriteAllText(temporary, PythonJson.Write(new DataObject(new[]
        {
            new KeyValuePair<string, DataValue>("way", new DataString(way)),
            new KeyValuePair<string, DataValue>("release", new DataString(release)),
        })), new UTF8Encoding(false));
        if (File.Exists(path))
        {
            File.Replace(temporary, path, null);
        }
        else
        {
            File.Move(temporary, path);
        }
    }

    public static bool HasMarker(string target) => File.Exists(Path.Combine(target, GameManifest.Folder, GameFiles.HelixMarker));

    private async Task<HelixGame> BridgeAsync(CancellationToken cancel, string command, params string[] arguments)
    {
        if (!Ready)
        {
            throw new UpscalerException("helixsr_missing");
        }

        var release = Release;
        var line = new List<string> { "-X", "utf8", Path.Combine(release, "setup", "helixsr_bridge.py"), release, command };
        line.AddRange(arguments);
        HelixProcessResult result;
        try
        {
            result = await process.RunAsync(Path.Combine(python, PythonExecutable), line, release, timeout, cancel).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is IOException or Win32Exception or TimeoutException or InvalidOperationException)
        {
            throw new UpscalerException(HelixBridge.FailedCode, exception.GetType().Name);
        }

        return HelixBridge.ParseAnswer(result.StandardOutput, result.StandardError);
    }

    private static string? Relative(string entry) =>
        entry.EndsWith("/", StringComparison.Ordinal) ? null : Normalize(entry);

    private static string Normalize(string entry)
    {
        if (entry.Contains("\\") || entry.Contains(":") || entry.StartsWith("/", StringComparison.Ordinal)
            || entry.Split('/').Any(part => part is ".." or "." or ""))
        {
            throw new UpscalerException("unsafe_archive");
        }

        return entry;
    }

    /// <summary>Extracts through a staging folder beside the destination and swaps it in only once complete.</summary>
    private void Unpack(string archive, string destination, Func<string, string?> map, string digest, string required, string missing)
    {
        var parent = Path.GetDirectoryName(destination)!;
        string? staging = null;
        string? saved = null;
        try
        {
            Directory.CreateDirectory(parent);
            var keep = Path.Combine(parent, ".replaced-" + Path.GetFileName(destination));
            if (!Directory.Exists(destination) && Directory.Exists(keep))
            {
                Rename(keep, destination);
            }

            if (Directory.Exists(keep))
            {
                DeleteTree(keep);
            }

            staging = Path.Combine(parent, ".unpack-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(staging);
            var root = Path.GetFullPath(staging) + Path.DirectorySeparatorChar;
            using (var zipped = ZipFile.OpenRead(archive))
            {
                foreach (var entry in zipped.Entries)
                {
                    if (map(entry.FullName) is not { } relative)
                    {
                        continue;
                    }

                    var path = Path.GetFullPath(Path.Combine(staging, relative.Replace('/', Path.DirectorySeparatorChar)));
                    if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    {
                        throw new UpscalerException("unsafe_archive");
                    }

                    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                    using var source = entry.Open();
                    using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1 << 18);
                    source.CopyTo(output);
                }
            }

            if (!File.Exists(Path.Combine(staging, required.Replace('/', Path.DirectorySeparatorChar))))
            {
                throw new UpscalerException("unpack_failed", missing);
            }

            File.WriteAllText(Path.Combine(staging, HelixRelease.Complete), digest, new UTF8Encoding(false));
            if (Directory.Exists(destination))
            {
                saved = keep;
                Rename(destination, saved);
            }

            try
            {
                Rename(staging, destination);
                staging = null;
            }
            catch
            {
                if (saved is not null && !Directory.Exists(destination))
                {
                    Rename(saved, destination);
                    saved = null;
                }

                throw;
            }
        }
        catch (Exception exception) when (exception is InvalidDataException or IOException or UnauthorizedAccessException)
        {
            throw new UpscalerException("unpack_failed", exception.GetType().Name);
        }
        finally
        {
            if (staging is not null)
            {
                DeleteTree(staging);
            }

            if (saved is not null && Directory.Exists(destination))
            {
                DeleteTree(saved);
            }
        }
    }

    /// <summary>A virus scanner holds a folder it has just seen written for a moment: the rename is retried before it fails.</summary>
    private void Rename(string source, string destination)
    {
        for (var attempt = 1; ; attempt++)
        {
            try
            {
                (MoveDirectory ?? Directory.Move)(source, destination);
                return;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException && attempt < RenameAttempts)
            {
                Thread.Sleep(RenameDelay * attempt);
            }
        }
    }

    private static void DeleteTree(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                foreach (var file in Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories))
                {
                    var attributes = File.GetAttributes(file);
                    if ((attributes & FileAttributes.ReadOnly) != 0)
                    {
                        File.SetAttributes(file, attributes & ~FileAttributes.ReadOnly);
                    }
                }

                Directory.Delete(path, true);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }
}
