using PanelDeControl.Core.Steam;

namespace PanelDeControl.Core.Upscalers;

/// <summary>The checks that stand between a request and a game folder.</summary>
public static class GameGuards
{
    /// <summary>Whether any process runs an image from inside the game's folder.</summary>
    public static bool IsRunningUnder(string root, IEnumerable<string> imagePaths)
    {
        var prefix = Normalize(root);
        if (prefix.Length == 0)
        {
            return false;
        }

        prefix += Path.DirectorySeparatorChar;
        return imagePaths.Any(path => Normalize(path).StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Install: Steam must be done with the game and the game must be closed.</summary>
    public static void EnsureCanInstall(SteamApp app, IEnumerable<string> imagePaths)
    {
        if (app.UpdateState is { } update)
        {
            throw new UpscalerException(update == SteamUpdateState.Running ? "updating" : "update_pending");
        }

        EnsureClosed(app, imagePaths);
    }

    public static void EnsureClosed(SteamApp app, IEnumerable<string> imagePaths)
    {
        if (IsRunningUnder(app.Root, imagePaths))
        {
            throw new UpscalerException("running");
        }
    }

    private static string Normalize(string path)
    {
        try
        {
            return Path.GetFullPath(path.Replace('/', Path.DirectorySeparatorChar)).TrimEnd(Path.DirectorySeparatorChar);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return "";
        }
    }
}

/// <summary>What the manifest in a game folder says about an install.</summary>
public sealed class ManifestCheck
{
    public ManifestCheck(bool present, bool complete, int files, IReadOnlyList<string> missing, IReadOnlyList<string> changed)
    {
        Present = present;
        Complete = complete;
        Files = files;
        Missing = missing;
        Changed = changed;
    }

    public bool Present { get; }

    /// <summary>False while an install is half done: the manifest is only a journal then.</summary>
    public bool Complete { get; }

    public int Files { get; }

    public IReadOnlyList<string> Missing { get; }

    public IReadOnlyList<string> Changed { get; }

    public bool Installed => Present && Complete;

    /// <summary>Reads the manifest only; no file is hashed.</summary>
    public static ManifestCheck Presence(string target)
    {
        var manifest = GameFiles.ReadManifest(target);
        return manifest is null
            ? new ManifestCheck(false, false, 0, Array.Empty<string>(), Array.Empty<string>())
            : new ManifestCheck(true, !manifest.Incomplete, manifest.Files.Count, Array.Empty<string>(), Array.Empty<string>());
    }

    /// <summary>Every listed file against its hash; a file without a hash (the INI, rewritten by Panel) only has to exist.</summary>
    public static ManifestCheck Verify(string target)
    {
        var manifest = GameFiles.ReadManifest(target);
        if (manifest is null)
        {
            return new ManifestCheck(false, false, 0, Array.Empty<string>(), Array.Empty<string>());
        }

        var missing = new List<string>();
        var changed = new List<string>();
        foreach (var pair in manifest.Files)
        {
            var path = Path.Combine(target, pair.Key.Replace('/', Path.DirectorySeparatorChar));
            try
            {
                if (!File.Exists(path))
                {
                    missing.Add(pair.Key);
                }
                else if (pair.Value is not null && GameFiles.Sha256(path) != pair.Value)
                {
                    changed.Add(pair.Key);
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                changed.Add(pair.Key);
            }
        }

        return new ManifestCheck(true, !manifest.Incomplete, manifest.Files.Count, missing, changed);
    }
}

/// <summary>The one long operation the companion runs at a time, as the widget polls it.</summary>
public sealed class UpscalerJobTracker
{
    private readonly object _lock = new();
    private UpscalerJobStatus? _job;

    public UpscalerJobStatus? Snapshot()
    {
        lock (_lock)
        {
            return _job is null ? null : Copy(_job);
        }
    }

    /// <summary>Starts a job, or throws <c>busy</c> while another one runs.</summary>
    public UpscalerJobStatus Begin(string kind, string appId)
    {
        lock (_lock)
        {
            if (_job is { State: UpscalerJobStates.Running })
            {
                throw new UpscalerException("busy");
            }

            _job = new UpscalerJobStatus { Id = Guid.NewGuid().ToString("N").Substring(0, 12), Kind = kind, AppId = appId };
            return Copy(_job);
        }
    }

    public void Stage(string stage, long? total = null)
    {
        lock (_lock)
        {
            if (_job is { State: UpscalerJobStates.Running })
            {
                _job.Stage = stage;
                if (total is { } size)
                {
                    _job.TotalBytes = size;
                }
            }
        }
    }

    public void Progress(long done)
    {
        lock (_lock)
        {
            if (_job is { State: UpscalerJobStates.Running })
            {
                _job.DoneBytes = done;
            }
        }
    }

    public void Finish()
    {
        lock (_lock)
        {
            if (_job is { State: UpscalerJobStates.Running })
            {
                _job.State = UpscalerJobStates.Done;
                _job.Stage = "done";
            }
        }
    }

    public void Fail(string error, string? detail = null)
    {
        lock (_lock)
        {
            if (_job is { State: UpscalerJobStates.Running })
            {
                _job.State = UpscalerJobStates.Error;
                _job.Error = error;
                _job.Detail = detail;
            }
        }
    }

    private static UpscalerJobStatus Copy(UpscalerJobStatus job) => new()
    {
        Id = job.Id,
        Kind = job.Kind,
        AppId = job.AppId,
        State = job.State,
        Stage = job.Stage,
        DoneBytes = job.DoneBytes,
        TotalBytes = job.TotalBytes,
        Error = job.Error,
        Detail = job.Detail,
    };
}
