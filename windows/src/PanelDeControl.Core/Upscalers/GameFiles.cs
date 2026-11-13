using System.Security.Cryptography;
using System.Text;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// Puts an upscaler's files into a game folder and takes them out again, leaving the game's own files exactly as they
/// were. Same steps and manifest as the Linux backend (<c>_apply_files</c>, <c>_remove_files</c>, <c>_recover_orphan</c>).
/// </summary>
public static class GameFiles
{
    public const string IniName = "OptiScaler.ini";
    public const string HelixMarker = "helixsr.json";

    /// <summary>Written by OptiScaler while the game runs: Panel saves the game's copy and drops its own.</summary>
    public static readonly IReadOnlyList<string> Generated = new[] { "OptiScaler.log" };

    /// <summary>Configs Panel seeds for a recipe tool (REFramework); not installed on Windows yet.</summary>
    private static readonly IReadOnlyList<string> Seeded = new[] { "re2_fw_config.txt" };

    private static readonly UTF8Encoding Utf8 = new(false);

    /// <param name="sources">Where each file goes, relative to <paramref name="target"/>, and the file it is copied from.</param>
    /// <param name="iniText">OptiScaler.ini as Panel writes it; null for the DLL mode, which only swaps FidelityFX DLLs.</param>
    /// <param name="copy">The file copy, replaceable so a test can fail it halfway.</param>
    public static GameManifest Apply(string target, IReadOnlyList<KeyValuePair<string, string>> sources, string? iniText,
        Action<string, string>? copy = null)
    {
        copy ??= (source, destination) => File.Copy(source, destination, false);
        var meta = Path.Combine(target, GameManifest.Folder);
        if (IsLink(meta))
        {
            throw new UpscalerException("unsafe_folder");
        }
        var backup = Path.Combine(meta, "backup");
        Directory.CreateDirectory(meta);
        var manifest = new GameManifest { Incomplete = true, Engine = iniText is null ? "dll" : null };
        var journal = Path.Combine(meta, GameManifest.FileName);
        // Every move is journaled before it happens, so an install killed mid-copy leaves a manifest that restores the
        // game's originals instead of mistaking Panel's own files for them on the next attempt.
        try
        {
            foreach (var pair in sources)
            {
                manifest.Set(pair.Key, null);
                Place(target, pair.Key, manifest, backup, journal);
                copy(pair.Value, Join(target, pair.Key));
                manifest.Set(pair.Key, Sha256(Join(target, pair.Key)));
            }
            if (iniText is not null)
            {
                manifest.Set(IniName, null);
                Place(target, IniName, manifest, backup, journal);
                File.WriteAllText(Join(target, IniName), iniText, Utf8);
                foreach (var generated in Generated)
                {
                    if (Exists(Join(target, generated)))
                    {
                        Place(target, generated, manifest, backup, journal);
                    }
                }
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            Save(journal, manifest);
            RemoveFiles(target);
            throw Translate(error);
        }
        manifest.Incomplete = false;
        Save(journal, manifest);
        return manifest;
    }

    /// <summary>Take an install out. Returns the files left in place because something else changed them since.</summary>
    public static IReadOnlyList<string> Remove(string target)
    {
        try
        {
            return RemoveFiles(target);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            throw Translate(error);
        }
    }

    /// <summary>Clear what no install claims: an interrupted install, or a removal that kept files the game replaced.</summary>
    public static void RecoverOrphan(string target, Func<string, bool> claimed)
    {
        var meta = Path.Combine(target, GameManifest.Folder);
        if (IsLink(meta) || !Directory.Exists(meta) || Exists(Path.Combine(meta, HelixMarker)) || claimed(target))
        {
            return;
        }
        try
        {
            if (File.Exists(Path.Combine(meta, GameManifest.FileName)))
            {
                RemoveFiles(target);
            }
            else
            {
                var backup = Path.Combine(meta, "backup");
                if (Directory.Exists(backup) && !IsLink(backup))
                {
                    var root = Path.GetFullPath(target);
                    foreach (var saved in Directory.GetFileSystemEntries(backup, "*", SearchOption.AllDirectories)
                                 .OrderByDescending(path => path, StringComparer.Ordinal))
                    {
                        if (!File.Exists(saved) || IsLink(saved))
                        {
                            continue;
                        }
                        var destination = Path.Combine(target, saved.Substring(backup.Length + 1));
                        if (!IsLink(destination) && Inside(Path.GetFullPath(destination), root))
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                            Replace(saved, destination);
                        }
                    }
                }
            }
            DeleteTree(meta);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            throw Translate(error);
        }
    }

    public static GameManifest? ReadManifest(string target)
    {
        try
        {
            return GameManifest.Parse(File.ReadAllText(Path.Combine(target, GameManifest.Folder, GameManifest.FileName), Utf8));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public static string Sha256(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 18);
        using var digest = SHA256.Create();
        var hash = digest.ComputeHash(stream);
        var text = new StringBuilder(hash.Length * 2);
        foreach (var value in hash)
        {
            text.Append(value.ToString("x2", System.Globalization.CultureInfo.InvariantCulture));
        }
        return text.ToString();
    }

    private static IReadOnlyList<string> RemoveFiles(string target)
    {
        var meta = Path.Combine(target, GameManifest.Folder);
        var manifest = ReadManifest(target);
        if (manifest is null)
        {
            return Array.Empty<string>();
        }
        if (manifest.HasConfiguration)
        {
            throw new UpscalerException("recipe_unsupported", "manifest restores recipe configuration");
        }
        var kept = new List<string>();
        foreach (var pair in manifest.Files)
        {
            var path = Join(target, pair.Key);
            if (!File.Exists(path))
            {
                continue;
            }
            var saved = Join(Path.Combine(meta, "backup"), pair.Key);
            if (pair.Value is null && manifest.Backups.Contains(pair.Key) && !Exists(saved))
            {
                continue;
            }
            if (Seeded.Contains(pair.Key))
            {
                throw new UpscalerException("recipe_unsupported", "manifest holds a seeded recipe config");
            }
            if (pair.Value is null || Sha256(path) == pair.Value)
            {
                File.Delete(path);
            }
            else
            {
                kept.Add(pair.Key);
            }
        }
        if (manifest.Engine != "dll")
        {
            foreach (var generated in Generated)
            {
                if (File.Exists(Join(target, generated)) && !manifest.Backups.Contains(generated))
                {
                    File.Delete(Join(target, generated));
                }
            }
        }
        foreach (var relative in manifest.Backups)
        {
            var saved = Join(Path.Combine(meta, "backup"), relative);
            if (Exists(saved) && !Exists(Join(target, relative)))
            {
                Replace(saved, Join(target, relative));
            }
        }
        foreach (var directory in manifest.Dirs.OrderByDescending(name => name.Length))
        {
            try
            {
                Directory.Delete(Join(target, directory), false);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
        if (kept.Count == 0)
        {
            DeleteTree(meta);
        }
        return kept;
    }

    private static void Place(string target, string relative, GameManifest manifest, string backup, string journal)
    {
        var parts = relative.Split('/');
        for (var depth = 1; depth < parts.Length; depth++)
        {
            var parent = string.Join("/", parts, 0, depth);
            if (!Exists(Join(target, parent)))
            {
                manifest.Dirs.Add(parent);
                Save(journal, manifest);
                Directory.CreateDirectory(Join(target, parent));
            }
        }
        var destination = Join(target, relative);
        if (Exists(destination))
        {
            var saved = Join(backup, relative);
            if (!manifest.Backups.Contains(relative))
            {
                manifest.Backups.Add(relative);
            }
            Save(journal, manifest);
            Directory.CreateDirectory(Path.GetDirectoryName(saved)!);
            if (Exists(saved))
            {
                // The oldest copy is the game's original; whatever sits in the game now came later.
                File.Delete(destination);
            }
            else
            {
                File.Move(destination, saved);
            }
        }
        else
        {
            Save(journal, manifest);
        }
    }

    private static void Save(string journal, GameManifest manifest)
    {
        var temporary = Path.Combine(Path.GetDirectoryName(journal)!, "." + GameManifest.FileName + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            File.WriteAllText(temporary, manifest.ToJson(), Utf8);
            Replace(temporary, journal);
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    /// <summary>Python's <c>os.replace</c>: move over an existing file.</summary>
    private static void Replace(string source, string destination)
    {
        if (File.Exists(destination))
        {
            File.Replace(source, destination, null);
        }
        else
        {
            File.Move(source, destination);
        }
    }

    private static void DeleteTree(string folder)
    {
        try
        {
            if (Directory.Exists(folder))
            {
                Directory.Delete(folder, true);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
    }

    /// <summary>A DLL the running game holds open cannot be replaced on Windows; a protected folder is never Panel's.</summary>
    private static Exception Translate(Exception error)
    {
        const int sharingViolation = 32;
        const int lockViolation = 33;
        var code = error.HResult & 0xFFFF;
        if (error is IOException && (code == sharingViolation || code == lockViolation))
        {
            return new UpscalerException("running", error.GetType().Name);
        }
        if (error is UnauthorizedAccessException)
        {
            return new UpscalerException("protected_folder", error.GetType().Name);
        }
        var detail = error.GetType().Name + ": " + error.Message;
        return new UpscalerException("write_failed", detail.Length > 200 ? detail.Substring(0, 200) : detail);
    }

    private static string Join(string root, string relative) => Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar));

    private static bool Exists(string path) => File.Exists(path) || Directory.Exists(path) || IsLink(path);

    private static bool IsLink(string path)
    {
        try
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }

    private static bool Inside(string path, string root)
    {
        var prefix = root.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal) ? root : root + Path.DirectorySeparatorChar;
        return path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
    }
}

public sealed class UpscalerException : Exception
{
    public UpscalerException(string code, string detail = "")
        : base(code)
    {
        Code = code;
        Detail = detail;
    }

    public string Code { get; }

    public string Detail { get; }
}
