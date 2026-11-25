using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// Choosing the executable, asking for the verdict and cancelling a job, as Linux's <c>set_exe</c>, <c>verify</c> and
/// <c>cancel</c> do.
/// </summary>
public sealed partial class UpscalerService
{
    private readonly object cancelLock = new();
    private CancellationTokenSource? jobCancel;

    private CancellationTokenSource NewJobCancel()
    {
        var source = new CancellationTokenSource();
        lock (cancelLock)
        {
            jobCancel = source;
        }

        return source;
    }

    private void ReleaseJobCancel(CancellationTokenSource source)
    {
        lock (cancelLock)
        {
            if (ReferenceEquals(jobCancel, source))
            {
                jobCancel = null;
            }

            source.Dispose();
        }
    }

    /// <summary>Only downloads and the checks before the game folder is touched listen: once files are being applied the job finishes.</summary>
    private UpscalersResponse Cancel()
    {
        var job = jobs.Snapshot();
        if (job is { State: UpscalerJobStates.Running })
        {
            lock (cancelLock)
            {
                jobCancel?.Cancel();
            }

            Record(job.AppId, "cancel", "requested", null, null);
        }

        return Ok(job: jobs.Snapshot());
    }

    private UpscalersResponse SetExe(string appId, string? exe)
    {
        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        string? relative = null;
        if (exe is not null)
        {
            relative = ExeOverride.Relative(app.Root, exe);
            if (relative is null || !fileSystem.IsFile(Path.Combine(app.Root, relative.Replace('/', Path.DirectorySeparatorChar))) || HasLink(app.Root, relative))
            {
                throw new UpscalerException("invalid_exe");
            }
        }

        lock (settingsLock)
        {
            EnsureNoJob(appId);
            store.SetExe(appId, relative);
            if (store.Install(appId) is { } stored)
            {
                WriteRecord(stored.Install, stored.InstalledAt);
            }
        }

        lock (scanLock)
        {
            scans.Remove(appId);
        }

        return Ok(game: Game(appId));
    }

    private bool HasLink(string root, string relative)
    {
        var path = root;
        foreach (var part in relative.Split('/'))
        {
            path = Path.Combine(path, part);
            if (fileSystem.IsSymbolicLink(path))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>The stored install, recovered from the game's own record first when Panel's data was wiped (as the game page does).</summary>
    private StoredUpscaler? Stored(string appId)
    {
        if (store.Install(appId) is { } stored)
        {
            return stored;
        }

        if (steam.Find(appId) is { } app)
        {
            Recover(app, Scan(app, null));
        }

        return store.Install(appId);
    }

    private UpscalersResponse Verify(string appId)
    {
        var stored = Stored(appId) ?? throw new UpscalerException("not_patched");
        var install = stored.Install;
        var verdict = UpscalerVerdict.Read(install, stored.InstalledAt);
        var result = IsInstalled(install) ? verdict?.Verdict ?? OptiScalerLog.NotRun : "broken";
        if (result != OptiScalerLog.NotRun)
        {
            try
            {
                store.SettleHistory(appId, install.Build, result, verdict?.Observed);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.history", exception.GetType().Name);
            }
        }

        return Ok(verify: new UpscalerVerification
        {
            Result = result,
            Verifiable = verdict is not null,
            Observed = verdict?.Observed,
            Provider = verdict?.Provider,
            Fallback = verdict?.Fallback,
        });
    }
}
