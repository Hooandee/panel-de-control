using System.Security.Cryptography;
using System.Text;
using PanelDeControl.Core.Data;
using static PanelDeControl.Core.Upscalers.InstallPaths;

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

    /// <summary>Configs Panel seeds for a recipe tool (REFramework); on removal only the keys Panel set go back.</summary>
    private static readonly IReadOnlyList<string> Seeded = new[] { ReframeworkConfig.FileName };

    private static readonly UTF8Encoding Utf8 = new(false);

    /// <param name="sources">Where each file goes, relative to <paramref name="target"/>, and the file it is copied from.</param>
    /// <param name="iniText">OptiScaler.ini as Panel writes it; null for the DLL mode, which only swaps FidelityFX DLLs.</param>
    /// <param name="copy">The file copy, replaceable so a test can fail it halfway.</param>
    /// <param name="protect">Leaves Panel's libraries and the saved originals read-only (a recipe's <c>protect_dlls</c>).</param>
    /// <param name="configuration">Keys Panel set per configuration file, journaled so removal puts back only those.</param>
    /// <param name="owned">Files that are Panel's whatever their hash later (a user's mod the game rewrites); removal takes them out regardless.</param>
    public static GameManifest Apply(string target, IReadOnlyList<KeyValuePair<string, string>> sources, string? iniText,
        Action<string, string>? copy = null, bool protect = false,
        IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>>? configuration = null, IEnumerable<string>? owned = null)
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
        if (owned is not null)
        {
            manifest.Owned.AddRange(owned.Distinct(StringComparer.Ordinal));
        }
        if (configuration is { Count: > 0 })
        {
            manifest.Configuration = new DataObject(configuration.Select(file => new KeyValuePair<string, DataValue>(file.Key,
                new DataObject(file.Value.Select(change => new KeyValuePair<string, DataValue>(change.Key, new DataString(change.Value))).ToList()))).ToList());
        }
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
        catch (Exception error)
        {
            Save(journal, manifest);
            RemoveFiles(target, false);
            if (error is IOException or UnauthorizedAccessException)
            {
                throw Translate(error);
            }
            throw;
        }
        manifest.Incomplete = false;
        manifest.ReadOnly = protect;
        Save(journal, manifest);
        if (protect)
        {
            ReadOnlyLibraries(target, manifest);
        }
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
                            Writable(saved);
                            Writable(destination);
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

    /// <param name="strict">False for a rollback, where an entry that points outside the game was never placed.</param>
    private static IReadOnlyList<string> RemoveFiles(string target, bool strict = true)
    {
        var meta = Path.Combine(target, GameManifest.Folder);
        var manifest = ReadManifest(target);
        if (manifest is null)
        {
            return Array.Empty<string>();
        }
        var record = Path.Combine(meta, PanelInstallRecord.FileName);
        try
        {
            if (File.Exists(record) && !IsLink(record))
            {
                File.Delete(record);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
        // One file that will not come out must not leave the game's backed-up originals out of it: each step is best
        // effort and a failure counts as kept, so the manifest stays for another attempt.
        var kept = new List<string>();
        UpscalerException? refused = null;
        foreach (var pair in manifest.Files)
        {
            try
            {
                if (!RemoveOne(target, meta, manifest, pair))
                {
                    kept.Add(pair.Key);
                }
            }
            catch (UpscalerException error) when (error.Code == "unsafe_folder")
            {
                refused ??= error;
            }
            catch (Exception)
            {
                kept.Add(pair.Key);
            }
        }
        if (manifest.Engine != "dll")
        {
            foreach (var generated in Generated)
            {
                try
                {
                    if (File.Exists(Join(target, generated)) && !manifest.Backups.Contains(generated))
                    {
                        File.Delete(Join(target, generated));
                    }
                }
                catch (Exception)
                {
                }
            }
        }
        foreach (var directory in manifest.Dirs.Where(name => name.Contains("custom/") && name.EndsWith("/dlssg", StringComparison.Ordinal)))
        {
            // ANR FG writes a log per launch beside its provider.
            try
            {
                var folder = Join(target, directory);
                if (Directory.Exists(folder) && !IsLink(folder))
                {
                    foreach (var log in Directory.GetFiles(folder, "nr_fg-*.log"))
                    {
                        File.Delete(log);
                    }
                }
            }
            catch (UpscalerException error) when (error.Code == "unsafe_folder")
            {
                refused ??= error;
            }
            catch (Exception)
            {
            }
        }
        foreach (var relative in manifest.Backups)
        {
            try
            {
                var saved = Join(Path.Combine(meta, "backup"), relative);
                if (Exists(saved) && !Exists(Join(target, relative)))
                {
                    Writable(saved);
                    Replace(saved, Join(target, relative));
                }
            }
            catch (UpscalerException error) when (error.Code == "unsafe_folder")
            {
                refused ??= error;
            }
            catch (Exception)
            {
                if (!kept.Contains(relative))
                {
                    kept.Add(relative);
                }
            }
        }
        foreach (var directory in manifest.Dirs.OrderByDescending(name => name.Length))
        {
            try
            {
                Directory.Delete(Join(target, directory), false);
            }
            catch (UpscalerException error) when (error.Code == "unsafe_folder")
            {
                refused ??= error;
            }
            catch (Exception)
            {
            }
        }
        if (refused is not null && strict)
        {
            throw refused;
        }
        if (kept.Count == 0)
        {
            DeleteTree(meta);
        }
        return kept;
    }

    /// <summary>Takes one manifest file out; false when it stays because something else changed it since.</summary>
    private static bool RemoveOne(string target, string meta, GameManifest manifest, KeyValuePair<string, string?> pair)
    {
        var path = Join(target, pair.Key);
        if (!File.Exists(path))
        {
            return true;
        }
        var saved = Join(Path.Combine(meta, "backup"), pair.Key);
        if (pair.Value is null && manifest.Backups.Contains(pair.Key) && !Exists(saved))
        {
            return true;
        }
        var seeded = Seeded.Contains(pair.Key);
        if (pair.Value is null || manifest.Owned.Contains(pair.Key) || Sha256(path) == pair.Value || (seeded && !manifest.Backups.Contains(pair.Key)))
        {
            Writable(path);
            File.Delete(path);
        }
        else if (manifest.Configuration is DataObject configuration && configuration.Get(pair.Key) is DataObject changes)
        {
            AutomaticRecipe.RestoreConfiguration(path, saved, changes.Members
                .Where(change => change.Value is DataString)
                .ToDictionary(change => change.Key, change => ((DataString)change.Value).Value, StringComparer.Ordinal));
        }
        else if (seeded)
        {
            // REFramework rewrote its config while installed: only the keys Panel set go back to the user's.
            var original = File.Exists(saved) && !IsLink(saved) ? File.ReadAllText(saved, Utf8) : "";
            var current = File.ReadAllText(path, Utf8);
            File.WriteAllText(path, ReframeworkConfig.WithKeys(current, ReframeworkConfig.Keys(original, ReframeworkConfig.AllKeys)), Utf8);
            if (File.Exists(saved))
            {
                Writable(saved);
                File.Delete(saved);
            }
        }
        else
        {
            return false;
        }
        return true;
    }

    /// <summary>Panel's own libraries and the game's backed-up originals; one Panel put over the game's stays writable for the updater.</summary>
    private static void ReadOnlyLibraries(string target, GameManifest manifest)
    {
        var paths = manifest.Files.Where(pair => !manifest.Backups.Contains(pair.Key)).Select(pair => Join(target, pair.Key)).ToList();
        var backup = Path.Combine(target, GameManifest.Folder, "backup");
        if (Directory.Exists(backup) && !IsLink(backup))
        {
            paths.AddRange(Directory.GetFiles(backup, "*", SearchOption.AllDirectories));
        }
        foreach (var path in paths.Where(path => string.Equals(Path.GetExtension(path), ".dll", StringComparison.OrdinalIgnoreCase)))
        {
            try
            {
                if (File.Exists(path) && !IsLink(path))
                {
                    File.SetAttributes(path, File.GetAttributes(path) | FileAttributes.ReadOnly);
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    private static void Writable(string path)
    {
        try
        {
            if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReadOnly) != 0)
            {
                File.SetAttributes(path, File.GetAttributes(path) & ~FileAttributes.ReadOnly);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
    }

    private static void Place(string target, string relative, GameManifest manifest, string backup, string journal)
    {
        var parts = relative.Split('/');
        for (var depth = 1; depth < parts.Length; depth++)
        {
            var parent = string.Join("/", parts, 0, depth);
            if (IsLink(Join(target, parent)))
            {
                throw new UpscalerException("unsafe_folder", "linked folder in the game");
            }
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
                foreach (var file in Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories))
                {
                    Writable(file);
                }
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

    /// <summary>
    /// A manifest entry under <paramref name="root"/>. The manifest sits in a folder anyone can edit, so an absolute
    /// path or a <c>..</c> in it would make Panel delete or move files elsewhere.
    /// </summary>
    private static string Join(string root, string relative)
    {
        var parts = relative.Split('/', '\\');
        if (relative.Length == 0 || Path.IsPathRooted(relative) || relative.Contains(':') || parts.Any(part => part is "" or "." or ".."))
        {
            throw new UpscalerException("unsafe_folder", "manifest path outside the game folder");
        }
        var full = Path.Combine(root, string.Join(Path.DirectorySeparatorChar.ToString(), parts));
        if (!Inside(Path.GetFullPath(full), Path.GetFullPath(root)))
        {
            throw new UpscalerException("unsafe_folder", "manifest path outside the game folder");
        }
        // A junction or symlink between the game folder and the file would carry it somewhere else.
        var folder = root;
        for (var depth = 0; depth < parts.Length - 1; depth++)
        {
            folder = Path.Combine(folder, parts[depth]);
            if (IsLink(folder))
            {
                throw new UpscalerException("unsafe_folder", "linked folder in the game");
            }
        }
        return full;
    }

    private static bool Exists(string path) => File.Exists(path) || Directory.Exists(path) || IsLink(path);

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
