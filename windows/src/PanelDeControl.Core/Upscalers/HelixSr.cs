using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What HelixSR's bridge reports about the game it installed into or removed from.</summary>
public sealed class HelixGame
{
    public HelixGame(string? exeFolder, string? logPath)
    {
        ExeFolder = exeFolder;
        LogPath = logPath;
    }

    public string? ExeFolder { get; }

    public string? LogPath { get; }
}

/// <summary>
/// HelixSR's JSON bridge as the Linux backend reads it (<c>helixsr.py</c>): the last line of its output that starts with
/// a brace is the answer, and anything but <c>ok</c> is <c>helixsr_failed</c> with the bridge's own words.
/// </summary>
public static class HelixBridge
{
    public const string FailedCode = "helixsr_failed";
    public const int DetailLimit = 200;

    private static readonly Regex NotInstalledText = new(@"^HelixSR( Scaler)? is not installed in ", RegexOptions.CultureInvariant);

    public static HelixGame ParseAnswer(string? standardOutput, string? standardError)
    {
        string? line = null;
        foreach (var candidate in (standardOutput ?? string.Empty).Split('\n'))
        {
            var text = candidate.TrimEnd('\r');
            if (text.StartsWith("{", StringComparison.Ordinal))
            {
                line = text;
            }
        }

        DataObject? answer = null;
        if (line is not null)
        {
            try
            {
                answer = DataValue.Parse(line) as DataObject;
            }
            catch (DataFormatException)
            {
            }
        }

        if (answer is null)
        {
            throw new UpscalerException(FailedCode, Tail((standardError ?? string.Empty).Trim(), DetailLimit));
        }

        if (!(answer.Get("ok") is DataBool { Value: true }))
        {
            var error = (answer.Get("error") as DataString)?.Value ?? string.Empty;
            throw new UpscalerException(FailedCode, error.Length > DetailLimit ? error.Substring(0, DetailLimit) : error);
        }

        var game = answer.Get("game") as DataObject;
        return new HelixGame(NonEmpty(game?.Get("exe_folder")), NonEmpty(game?.Get("log_path")));
    }

    /// <summary>The bridge's answer once HelixSR's DLL is gone, usually replaced by a game update.</summary>
    public static bool NotInstalled(string? detail) => NotInstalledText.IsMatch(detail ?? string.Empty);

    private static string? NonEmpty(DataValue? value) => value is DataString { Value.Length: > 0 } text ? text.Value : null;

    private static string Tail(string text, int length) => text.Length > length ? text.Substring(text.Length - length) : text;
}

/// <summary>
/// How HelixSR's official release ZIP is unpacked: only its <c>HelixSR-x.y.z/</c> folder, as it is, never anything that
/// would leave that folder. HelixSR's licence forbids changing or redistributing its files.
/// </summary>
public static class HelixRelease
{
    public const string Complete = ".panel-complete";
    public const string Current = "current";
    public const string Bridge = "setup/helixsr_bridge.py";

    private static readonly Regex ReleaseName = new(@"^HelixSR-[0-9]+\.[0-9]+\.[0-9]+\z", RegexOptions.CultureInvariant);
    private static readonly Regex Digest = new(@"^[0-9a-f]{64}\z", RegexOptions.CultureInvariant);

    /// <summary>The release folder an archive carries, from its file name; <paramref name="fallback"/> for any other name.</summary>
    public static string NameOf(string archiveFileName, string fallback)
    {
        var name = Path.GetFileNameWithoutExtension(archiveFileName);
        return IsReleaseName(name) ? name : fallback;
    }

    public static bool IsReleaseName(string? name) => name is not null && ReleaseName.IsMatch(name);

    public static bool IsDigest(string? text) => text is not null && Digest.IsMatch(text);

    /// <summary>
    /// Where an archive entry goes inside the unpacked release (always <c>/</c>-separated), or null when the entry is not
    /// part of the release folder or is a directory. Throws <c>unsafe_archive</c> for a path that would leave the folder.
    /// </summary>
    public static string? Destination(string entryName, string release)
    {
        var prefix = release + "/";
        if (!entryName.StartsWith(prefix, StringComparison.Ordinal) || entryName.EndsWith("/", StringComparison.Ordinal))
        {
            return null;
        }

        var relative = entryName.Substring(prefix.Length);
        if (relative.Length == 0 || relative.Contains("\\") || relative.Contains(":") || relative.StartsWith("/", StringComparison.Ordinal)
            || relative.Split('/').Any(part => part is ".." or "." or ""))
        {
            throw new UpscalerException("unsafe_archive");
        }

        return relative;
    }
}

/// <summary>What HelixSR's own <c>HLX_FSR.log</c> says, as the Linux game page reads it (<c>read_log</c> and <c>verdict</c>).</summary>
public sealed class HelixLogFacts
{
    public bool Present { get; internal set; }

    /// <summary>Every log found predates the install.</summary>
    public bool Stale { get; internal set; }

    public string? Path { get; internal set; }

    /// <summary>"HLX FSR 4" once its runtime logged a context.</summary>
    public string? Upscaler { get; internal set; }

    public int[]? Output { get; internal set; }
}

public static class HelixLog
{
    public const string FileName = "HLX_FSR.log";
    public const int MaximumBytes = 2 * 1024 * 1024;
    public const string UpscalerName = "HLX FSR 4";
    public const string Storage = "_storage_";
    public const string StorageProvider = "amd_fidelityfx_upscaler_dx12.dll";

    // HLX FSR 4 logs its context once with the largest render size the game may send, so it proves HLX runs but not the real input size.
    private static readonly Regex Active = new(
        @"HLX-FSR-4 own runtime active: .*?output ([0-9]{2,5})x([0-9]{2,5}), max render ([0-9]{2,5})x([0-9]{2,5})",
        RegexOptions.CultureInvariant);

    /// <summary>The newest facts among the candidate logs; one that predates <paramref name="since"/> only counts as stale.</summary>
    public static HelixLogFacts Read(IEnumerable<string> logs, DateTime? since)
    {
        var facts = new HelixLogFacts();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var candidates = logs.ToList();
        foreach (var log in candidates.Concat(candidates.Select(path => System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path) ?? string.Empty, FileName))))
        {
            if (!seen.Add(log) || Load(log) is not { } loaded)
            {
                continue;
            }

            if (since is { } floor && loaded.Modified < floor)
            {
                if (!facts.Present)
                {
                    facts.Stale = true;
                }

                continue;
            }

            facts.Present = true;
            facts.Stale = false;
            facts.Path ??= log;
            foreach (var line in loaded.Text.Split('\n', '\r'))
            {
                if (Active.Match(line) is { Success: true } match)
                {
                    facts.Upscaler = UpscalerName;
                    facts.Path = log;
                    facts.Output = new[]
                    {
                        int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture),
                        int.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture),
                    };
                }
            }
        }

        return facts;
    }

    /// <summary>
    /// The logs of one Panel install: the bridge's own, and the runtime's under <c>_storage_</c> once HelixSR's marker and
    /// provider prove HelixSR is still in the game. Reads nothing through a link.
    /// </summary>
    public static HelixLogFacts ReadInstall(InstalledUpscaler install, double installedAt)
    {
        if (install.Engine != "helixsr")
        {
            return new HelixLogFacts();
        }

        var logs = new List<string>();
        if (install.Log.Length > 0)
        {
            logs.Add(install.Log);
        }

        var since = UpscalerVerdict.Since(installedAt);
        if (since is not null && install.Target.Length > 0 && install.HelixFile.Length > 0)
        {
            var storage = System.IO.Path.Combine(install.Target, Storage);
            var runtime = System.IO.Path.Combine(storage, FileName);
            if (File.Exists(install.HelixFile) && IsPlain(storage, true) && File.Exists(System.IO.Path.Combine(storage, StorageProvider)) && IsPlain(runtime, false))
            {
                logs.Add(runtime);
            }
        }

        return Read(logs, since);
    }

    /// <summary><c>not_run</c> until a fresh log says more; <c>active</c> once HLX FSR 4 created a context, else <c>loaded</c>.</summary>
    public static string Verdict(HelixLogFacts facts)
    {
        if (!facts.Present || facts.Stale)
        {
            return OptiScalerLog.NotRun;
        }

        return facts.Upscaler is not null ? "active" : "loaded";
    }

    private static bool IsPlain(string path, bool directory)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            return (attributes & FileAttributes.ReparsePoint) == 0 && ((attributes & FileAttributes.Directory) != 0) == directory;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static (string Text, DateTime Modified)? Load(string path)
    {
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return null;
            }

            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var length = stream.Length;
            if (length > MaximumBytes)
            {
                stream.Seek(length - MaximumBytes, SeekOrigin.Begin);
            }

            using var memory = new MemoryStream();
            stream.CopyTo(memory);
            return (new UTF8Encoding(false, false).GetString(memory.ToArray()), info.LastWriteTimeUtc);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }
}

/// <summary>Takes HelixSR's drop-in out of a game without its bridge, never putting an old backup over a game update.</summary>
public static class HelixRestore
{
    public const string Record = "helixsr-install.json";
    private const string Settings = "helixsr.ini";

    private static readonly byte[][] Signatures = { Encoding.ASCII.GetBytes("HLX-FSR-4"), Encoding.ASCII.GetBytes("HelixSR") };

    /// <summary>False when a HelixSR DLL has no backup of the game's own, which nothing here can bring back.</summary>
    public static bool ByHand(string folder)
    {
        var stuck = false;
        foreach (var swap in RecordedSwaps(folder))
        {
            var backup = IsRegular(swap.Original);
            var exists = File.Exists(swap.Current) || IsLink(swap.Current);
            if (!exists)
            {
                if (backup)
                {
                    Move(swap.Original, swap.Current);
                }
            }
            else if (IsHelixFile(swap.Current))
            {
                if (backup)
                {
                    Move(swap.Original, swap.Current);
                }
                else if (System.IO.Path.GetFileName(swap.Current).StartsWith("amd_fidelityfx_", StringComparison.OrdinalIgnoreCase))
                {
                    stuck = true;
                }
            }
            else if (backup && SameFile(swap.Original, swap.Current))
            {
                Writable(swap.Original);
                File.Delete(swap.Original);
            }
        }

        if (stuck)
        {
            return false;
        }

        foreach (var name in new[] { Record, Settings })
        {
            var path = System.IO.Path.Combine(folder, name);
            if (File.Exists(path) || IsLink(path))
            {
                Writable(path);
                File.Delete(path);
            }
        }

        return true;
    }

    internal static IReadOnlyList<(string Current, string Original)> RecordedSwaps(string folder)
    {
        var swaps = new List<(string, string)>();
        try
        {
            var path = System.IO.Path.Combine(folder, Record);
            var info = new FileInfo(path);
            if (!info.Exists || info.Length > 1024 * 1024 || (info.Attributes & FileAttributes.ReparsePoint) != 0
                || DataValue.Parse(File.ReadAllText(path, new UTF8Encoding(false, false))) is not DataObject record
                || record.Get("files") is not DataArray files)
            {
                return swaps;
            }

            foreach (var name in files.Items.OfType<DataString>().Select(item => item.Value))
            {
                if (name.Length == 0 || name is "." or ".." || System.IO.Path.GetFileName(name) != name || name.IndexOfAny(new[] { '/', '\\', ':' }) >= 0)
                {
                    continue;
                }

                swaps.Add((System.IO.Path.Combine(folder, name), System.IO.Path.Combine(folder, System.IO.Path.ChangeExtension(name, ".original.dll"))));
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DataFormatException)
        {
        }

        return swaps;
    }

    private static void Move(string source, string destination)
    {
        Writable(source);
        if (File.Exists(destination))
        {
            Writable(destination);
            File.Replace(source, destination, null);
        }
        else
        {
            File.Move(source, destination);
        }
    }

    private static void Writable(string path)
    {
        try
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReadOnly) != 0)
            {
                File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    private static bool IsLink(string path)
    {
        try
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static bool IsRegular(string path) => File.Exists(path) && !IsLink(path);

    private static bool SameFile(string a, string b)
    {
        try
        {
            if (IsLink(a) || IsLink(b) || new FileInfo(a).Length != new FileInfo(b).Length)
            {
                return false;
            }

            return GameFiles.Sha256(a) == GameFiles.Sha256(b);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    /// <summary>HelixSR's drop-in carries these strings (3.2.0 and 3.3.0); AMD's FidelityFX DLLs never do.</summary>
    public static bool IsHelixFile(string path)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1 << 20);
            var overlap = Signatures.Max(signature => signature.Length) - 1;
            var buffer = new byte[(1 << 20) + overlap];
            var kept = 0;
            int read;
            while ((read = stream.Read(buffer, kept, buffer.Length - kept)) > 0)
            {
                var total = kept + read;
                if (Signatures.Any(signature => IndexOf(buffer, total, signature) >= 0))
                {
                    return true;
                }

                kept = Math.Min(overlap, total);
                Buffer.BlockCopy(buffer, total - kept, buffer, 0, kept);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }

        return false;
    }

    private static int IndexOf(byte[] data, int length, byte[] pattern)
    {
        for (var start = 0; start <= length - pattern.Length; start++)
        {
            var index = 0;
            while (index < pattern.Length && data[start + index] == pattern[index])
            {
                index++;
            }

            if (index == pattern.Length)
            {
                return start;
            }
        }

        return -1;
    }
}
