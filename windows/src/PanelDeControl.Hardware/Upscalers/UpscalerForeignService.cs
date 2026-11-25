using System.Text;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// Setting another tool's OptiScaler aside and putting it back, as Linux's <c>adopt_foreign</c> and <c>restore_foreign</c>
/// do. The files go to a folder under Panel's state, recorded before the first move and after every item.
/// </summary>
public sealed partial class UpscalerService
{
    private const long OptiScalerScanLimit = 96L * 1024 * 1024;
    private const int ScanChunk = 1024 * 1024;

    private static readonly string[] ForeignItemNames =
    {
        "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "D3D12_Optiscaler", "D3D12_OptiScaler", "FRAMEGEN_PATCH",
        "helixsr-install.json", "HelixSR-Scaler.files", "helixsr.ini", "helixsr.log", "HLX_FSR.log",
    };

    private string StateFolder => Path.GetDirectoryName(Path.GetFullPath(store.FilePath))!;

    private string ForeignRoot => Path.Combine(StateFolder, "foreign");

    private UpscalersResponse AdoptForeign(string appId)
    {
        lock (settingsLock)
        {
            var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
            EnsureNoJob(appId);
            GameGuards.EnsureCanInstall(app, runningImages());
            var analysis = Scan(app, null, force: true);
            if (Stored(appId) is not null || PanelFolder(app, analysis) is not null)
            {
                throw new UpscalerException("still_patched");
            }

            var target = analysis.Target is { } found ? Path.GetFullPath(found) : throw new UpscalerException("unsupported_layout");
            if (ForeignUpscalerIdentity.Read(fileSystem, target).Engine == "helixsr")
            {
                throw new UpscalerException("foreign_helix");
            }

            var items = ForeignItems(target);
            var swaps = HelixSwaps(target);
            if (items.Count == 0 && swaps.Count == 0)
            {
                throw new UpscalerException("no_foreign");
            }

            if (TraversesLink(app.Root, target) || items.Any(name => ContainsLink(Path.Combine(target, name))))
            {
                throw new UpscalerException("unsupported_layout");
            }

            var folder = NewBackupFolder(appId);
            if (TraversesLink(StateFolder, folder))
            {
                throw new UpscalerException("unsupported_layout");
            }

            Directory.CreateDirectory(folder);
            var record = new ForeignBackup { Dir = folder, Target = target, At = clock() };
            SaveForeignBackup(appId, record);
            foreach (var name in items)
            {
                MoveEntry(Path.Combine(target, name), Path.Combine(folder, name));
                record.Items.Add(name);
                SaveForeignBackup(appId, record);
            }

            foreach (var name in swaps)
            {
                var current = Path.Combine(target, name);
                var original = Path.Combine(target, Path.ChangeExtension(name, ".original.dll"));
                if (Present(current))
                {
                    MoveEntry(current, Path.Combine(folder, name));
                }

                MoveEntry(original, current, overwrite: true);
                record.Swaps.Add(name);
                SaveForeignBackup(appId, record);
            }

            ForgetScan(appId);
            Record(appId, "adopt_foreign", "done", null, null);
            return Ok(moved: record.Items.Concat(record.Swaps).ToArray());
        }
    }

    private UpscalersResponse RestoreForeign(string appId)
    {
        lock (settingsLock)
        {
            var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
            EnsureNoJob(appId);
            var record = ForeignBackupOf(app, Scan(app, null).Target) ?? throw new UpscalerException("no_foreign");
            if (Stored(appId) is not null)
            {
                throw new UpscalerException("still_patched");
            }

            GameGuards.EnsureClosed(app, runningImages());
            record.Target = InstallRelocation.Relocated(record.Target, record.Target, app.Root);
            if (!record.HasValidNames || !IsInside(record.Dir, ForeignRoot) || !IsInside(record.Target, app.Root) && !SamePath(record.Target, app.Root)
                || TraversesLink(app.Root, record.Target) || TraversesLink(StateFolder, record.Dir) || !Directory.Exists(record.Target))
            {
                throw new UpscalerException("unsupported_layout");
            }

            var target = record.Target;
            var backup = record.Dir;
            var restored = new List<string>();
            var kept = new List<string>();
            foreach (var name in record.Swaps.ToList())
            {
                var current = Path.Combine(target, name);
                if (Present(current))
                {
                    MoveEntry(current, Path.Combine(target, Path.ChangeExtension(name, ".original.dll")), overwrite: true);
                }

                if (Present(Path.Combine(backup, name)))
                {
                    MoveEntry(Path.Combine(backup, name), current);
                }

                restored.Add(name);
                record.Swaps.Remove(name);
                SaveForeignBackup(appId, record);
            }

            foreach (var name in record.Items.ToList())
            {
                if (Present(Path.Combine(target, name)))
                {
                    kept.Add(name);
                    continue;
                }

                if (Present(Path.Combine(backup, name)))
                {
                    MoveEntry(Path.Combine(backup, name), Path.Combine(target, name));
                }

                restored.Add(name);
                record.Items.Remove(name);
                SaveForeignBackup(appId, record);
            }

            ForgetScan(appId);
            if (kept.Count > 0)
            {
                Record(appId, "restore_foreign", "partial", null, null);
                return Ok(restored: restored.ToArray(), kept: kept.ToArray());
            }

            try
            {
                Directory.Delete(backup, true);
                var parent = Path.GetDirectoryName(backup)!;
                if (!Directory.EnumerateFileSystemEntries(parent).Any())
                {
                    Directory.Delete(parent);
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.foreign", exception.GetType().Name);
            }

            store.SetForeignBackup(appId, null);
            Record(appId, "restore_foreign", "done", null, null);
            return Ok(restored: restored.ToArray());
        }
    }

    /// <summary>The backup Panel recorded for this game, or one found in its own folder with a record for this very game folder (Panel's state was wiped).</summary>
    private ForeignBackup? ForeignBackupOf(SteamApp app, string? target)
    {
        if (store.ForeignBackupOf(app.AppId) is { } recorded)
        {
            return recorded;
        }

        var parent = Path.Combine(ForeignRoot, app.AppId);
        if (target is null || !Directory.Exists(parent) || TraversesLink(StateFolder, parent))
        {
            return null;
        }

        IEnumerable<string> folders;
        try
        {
            folders = Directory.EnumerateDirectories(parent)
                .OrderByDescending(folder => long.TryParse(Path.GetFileName(folder), out var stamp) ? stamp : 0)
                .ThenBy(folder => folder, StringComparer.Ordinal)
                .ToList();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }

        foreach (var folder in folders)
        {
            if (ForeignBackup.ReadSidecar(folder) is not { } found || !SamePath(found.Target, target) || (File.GetAttributes(folder) & FileAttributes.ReparsePoint) != 0)
            {
                continue;
            }

            found.Dir = folder;
            try
            {
                store.SetForeignBackup(app.AppId, found);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.foreign", exception.GetType().Name);
            }

            return found;
        }

        return null;
    }

    private UpscalerForeignBackup? ForeignBackupReport(SteamApp app, string? target)
    {
        try
        {
            return ForeignBackupOf(app, target) is { } backup ? new UpscalerForeignBackup { At = (long)backup.At } : null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.foreign", exception.GetType().Name);
            return null;
        }
    }

    private void SaveForeignBackup(string appId, ForeignBackup record)
    {
        store.SetForeignBackup(appId, record);
        record.WriteSidecar();
    }

    private void ForgetScan(string appId)
    {
        lock (scanLock)
        {
            scans.Remove(appId);
        }
    }

    private string NewBackupFolder(string appId)
    {
        var stamp = (long)clock();
        string folder;
        do
        {
            folder = Path.Combine(ForeignRoot, appId, stamp++.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }
        while (Present(folder));
        return folder;
    }

    /// <summary>Other tools' files beside the exe, by the names they have on disk: the fixed list plus proxies whose own bytes say OptiScaler.</summary>
    private List<string> ForeignItems(string target)
    {
        var entries = fileSystem.List(target);
        var found = new List<string>();
        foreach (var wanted in ForeignItemNames)
        {
            if (entries.FirstOrDefault(entry => string.Equals(entry.Name, wanted, StringComparison.OrdinalIgnoreCase)) is { } entry
                && !found.Contains(entry.Name, StringComparer.OrdinalIgnoreCase))
            {
                found.Add(entry.Name);
            }
        }

        foreach (var proxy in ForeignUpscalerIdentity.ProxyNames)
        {
            if (entries.FirstOrDefault(entry => string.Equals(entry.Name, proxy, StringComparison.OrdinalIgnoreCase)) is { IsDirectory: false } entry
                && MentionsOptiScaler(Path.Combine(target, entry.Name)))
            {
                found.Add(entry.Name);
            }
        }

        return found;
    }

    /// <summary>Game libraries HelixSR replaced, whose originals wait beside them as <c>*.original.dll</c>.</summary>
    private static List<string> HelixSwaps(string target) =>
        HelixRestore.RecordedSwaps(target)
            .Where(swap => File.Exists(swap.Original))
            .Select(swap => Path.GetFileName(swap.Current))
            .ToList();

    private bool MentionsOptiScaler(string path)
    {
        var needle = Encoding.ASCII.GetBytes("OptiScaler");
        var buffer = new byte[ScanChunk + needle.Length];
        try
        {
            using var stream = fileSystem.OpenRead(path);
            if (stream is null)
            {
                return false;
            }

            var kept = 0;
            long total = 0;
            while (total < OptiScalerScanLimit)
            {
                var count = stream.Read(buffer, kept, ScanChunk);
                if (count <= 0)
                {
                    return false;
                }

                total += count;
                var length = kept + count;
                if (buffer.AsSpan(0, length).IndexOf(needle) >= 0)
                {
                    return true;
                }

                kept = Math.Min(needle.Length - 1, length);
                Array.Copy(buffer, length - kept, buffer, 0, kept);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }

        return false;
    }

    private static bool Present(string path)
    {
        try
        {
            _ = File.GetAttributes(path);
            return true;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return exception is UnauthorizedAccessException;
        }
    }

    /// <summary>Whether any folder from <paramref name="root"/> (left out) down to <paramref name="path"/> is a link, or the path is not under the root.</summary>
    private bool TraversesLink(string root, string path)
    {
        var relative = Path.GetRelativePath(root, path);
        if (relative == ".")
        {
            return false;
        }

        if (relative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(relative))
        {
            return true;
        }

        var current = root;
        foreach (var part in relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            current = Path.Combine(current, part);
            if (fileSystem.IsSymbolicLink(current))
            {
                return true;
            }
        }

        return false;
    }

    private bool ContainsLink(string path)
    {
        if (fileSystem.IsSymbolicLink(path))
        {
            return true;
        }

        return fileSystem.IsDirectory(path)
            && fileSystem.List(path).Any(entry => entry.IsSymbolicLink || entry.IsDirectory && ContainsLink(Path.Combine(path, entry.Name)));
    }

    private static bool IsInside(string path, string root)
    {
        var prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return Path.GetFullPath(path).StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>A move that also works across volumes: a folder that cannot be renamed is copied and then removed.</summary>
    private static void MoveEntry(string source, string destination, bool overwrite = false)
    {
        if (Directory.Exists(source))
        {
            try
            {
                Directory.Move(source, destination);
            }
            catch (IOException) when (Directory.Exists(source) && !Directory.Exists(destination))
            {
                CopyTree(source, destination);
                ClearReadOnly(source);
                Directory.Delete(source, true);
            }

            return;
        }

        ClearReadOnly(source);
        if (overwrite && File.Exists(destination))
        {
            ClearReadOnly(destination);
        }

        File.Move(source, destination, overwrite);
    }

    private static void CopyTree(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.GetFiles(source))
        {
            File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), false);
        }

        foreach (var folder in Directory.GetDirectories(source))
        {
            CopyTree(folder, Path.Combine(destination, Path.GetFileName(folder)));
        }
    }

    private static void ClearReadOnly(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                foreach (var entry in Directory.EnumerateFileSystemEntries(path, "*", SearchOption.AllDirectories))
                {
                    ClearReadOnlyAttribute(entry);
                }
            }

            ClearReadOnlyAttribute(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    private static void ClearReadOnlyAttribute(string path)
    {
        var attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.ReadOnly) != 0)
        {
            File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
        }
    }
}
