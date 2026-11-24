using System.Diagnostics;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

public interface IUpscalersController
{
    Task<UpscalersResponse> HandleAsync(UpscalersRequest request, CancellationToken cancellationToken);
}

/// <summary>
/// What the widget asks of upscalers: reads answer at once, install and uninstall start the one background job the
/// widget then polls. Everything reported is read back from the game's manifest, never taken from what was asked.
/// </summary>
public sealed class UpscalerService : IUpscalersController
{
    public static readonly TimeSpan OverviewScanBudget = TimeSpan.FromSeconds(3);

    private const string Platform = "windows";
    private const string Arch = "amd64";

    private readonly UpscalerData data;
    private readonly UpscalerStateStore store;
    private readonly AssetCache cache;
    private readonly IReadOnlyFileSystem fileSystem;
    private readonly SteamGames steam;
    private readonly Func<IReadOnlyList<string>> runningImages;
    private readonly Func<GpuFamilyResult> readGpu;
    private readonly Func<string?> readDevice;
    private readonly Func<double> clock;
    private readonly Action<string, string> log;
    private readonly UpscalerJobTracker jobs = new();
    private readonly object scanLock = new();
    private readonly Dictionary<string, (long Stamp, GameAnalysis Analysis)> scans = new(StringComparer.Ordinal);
    private readonly Lazy<GpuFamilyResult> gpu;
    private readonly Lazy<string?> device;
    private readonly Func<Func<Task>, Task> start;
    private readonly Func<byte[], int, ScaledCover?> scaleCover;
    private readonly ISteamLaunchOptions? launchOptions;
    private readonly Func<string?> vcRuntime;
    private readonly Dictionary<string, (double Until, UpscalerCover? Cover)> covers = new(StringComparer.Ordinal);
    private readonly object coverLock = new();

    /// <param name="start">Starts the background job; replaceable so a test can run it inline.</param>
    public UpscalerService(
        UpscalerData data,
        UpscalerStateStore store,
        AssetCache cache,
        IReadOnlyFileSystem fileSystem,
        SteamGames steam,
        Func<IReadOnlyList<string>> runningImages,
        Func<GpuFamilyResult> readGpu,
        Func<string?> readDevice,
        Func<double>? clock = null,
        Action<string, string>? log = null,
        Func<Func<Task>, Task>? start = null,
        Func<byte[], int, ScaledCover?>? scaleCover = null,
        ISteamLaunchOptions? launchOptions = null,
        Func<string?>? vcRuntime = null)
    {
        this.data = data;
        this.store = store;
        this.cache = cache;
        this.fileSystem = fileSystem;
        this.steam = steam;
        this.runningImages = runningImages;
        this.readGpu = readGpu;
        this.readDevice = readDevice;
        this.clock = clock ?? (() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0);
        this.log = log ?? ((step, detail) => CompanionLog.Write(step, detail));
        this.start = start ?? (job => Task.Run(job));
        this.scaleCover = scaleCover ?? CoverImages.Scale;
        this.launchOptions = launchOptions;
        this.vcRuntime = vcRuntime ?? (() => null);
        gpu = new Lazy<GpuFamilyResult>(() => this.readGpu());
        device = new Lazy<string?>(() => this.readDevice());
    }

    public UpscalerJobStatus? Job => jobs.Snapshot();

    public GpuFamilyResult Gpu => gpu.Value;

    public string? Device => device.Value;

    public async Task<UpscalersResponse> HandleAsync(UpscalersRequest request, CancellationToken cancellationToken)
    {
        try
        {
            switch (request.Operation)
            {
                case UpscalersOperation.Overview:
                    return Ok(overview: await Task.Run(Overview, cancellationToken).ConfigureAwait(false));
                case UpscalersOperation.Job:
                    return Ok();
                case UpscalersOperation.Cover:
                    return Ok(cover: await Task.Run(() => Cover(request.AppId!), cancellationToken).ConfigureAwait(false)
                        ?? throw new UpscalerException("no_cover"));
                case UpscalersOperation.Game:
                    return Ok(game: await Task.Run(() => Game(request.AppId!), cancellationToken).ConfigureAwait(false));
                case UpscalersOperation.Install:
                    if (!request.ExperimentalEnabled)
                    {
                        return UpscalersResponse.Rejected("experimental_required", jobs.Snapshot());
                    }

                    return await Task.Run(() => BeginInstall(request), cancellationToken).ConfigureAwait(false);
                case UpscalersOperation.Uninstall:
                    if (!request.ExperimentalEnabled)
                    {
                        return UpscalersResponse.Rejected("experimental_required", jobs.Snapshot());
                    }

                    return await Task.Run(() => BeginUninstall(request.AppId!), cancellationToken).ConfigureAwait(false);
                default:
                    return UpscalersResponse.Rejected("unsupported_operation", jobs.Snapshot());
            }
        }
        catch (UpscalerException exception)
        {
            return UpscalersResponse.Rejected(exception.Code, jobs.Snapshot());
        }
        catch (AssetException exception)
        {
            return UpscalersResponse.Rejected(exception.Code, jobs.Snapshot());
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            log($"upscalers.{request.Operation}", exception.ToString());
            return UpscalersResponse.Fault(exception is IOException or UnauthorizedAccessException ? "upscalers_storage_failed" : "upscalers_failed", jobs.Snapshot());
        }
    }

    public UpscalersOverview Overview()
    {
        var result = Gpu;
        var libraries = steam.Libraries();
        IReadOnlyList<string>? images = null;
        try
        {
            images = runningImages();
        }
        catch (UpscalerException)
        {
        }

        var clockWatch = Stopwatch.StartNew();
        var rows = new List<UpscalerGameSummary>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var app in steam.All())
        {
            seen.Add(app.AppId);
            var row = Summary(app, images);
            if (row.State == UpscalerGameStates.None)
            {
                if (clockWatch.Elapsed > OverviewScanBudget)
                {
                    row.Scanned = false;
                }
                else
                {
                    var analysis = Scan(app, null);
                    if (Recover(app, analysis) is { } recovered)
                    {
                        row = recovered == UpscalerGameStates.Installed ? Summary(app, images) : WithState(row, recovered);
                    }
                    else if (analysis.Foreign)
                    {
                        row.State = UpscalerGameStates.Foreign;
                    }
                }
            }

            rows.Add(row);
        }

        foreach (var appId in store.InstalledAppIds.Where(id => !seen.Contains(id)))
        {
            rows.Add(new UpscalerGameSummary
            {
                AppId = appId,
                Name = appId,
                State = UpscalerGameStates.Missing,
                Build = store.Install(appId)!.Install.Build,
                Version = data.Catalog.Build(store.Install(appId)!.Install.Build)?.Version,
                Label = UpscalerLabel.Badge(data.Catalog.Build(store.Install(appId)!.Install.Build), store.Install(appId)!.Install.Options.Model),
            });
        }

        return new UpscalersOverview
        {
            Gpu = result.Generation,
            GpuSource = result.Source,
            Device = Device,
            GpuName = result.Name,
            SteamFound = libraries.Count > 0,
            Games = rows.ToArray(),
        };
    }

    public UpscalerGameDetail Game(string appId)
    {
        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        IReadOnlyList<string>? images = null;
        try
        {
            images = runningImages();
        }
        catch (UpscalerException)
        {
        }

        var recipe = Recipe(app);
        var analysis = Scan(app, recipe, force: true);
        var summary = Summary(app, images);
        if (summary.State == UpscalerGameStates.None)
        {
            if (Recover(app, analysis) is { } recovered)
            {
                summary = recovered == UpscalerGameStates.Installed ? Summary(app, images) : WithState(summary, recovered);
            }
            else if (analysis.Foreign)
            {
                summary.State = UpscalerGameStates.Foreign;
            }
        }

        var generation = Gpu.Generation;
        var builds = UpscalerPlanner.Describe(data.Catalog, generation, Device ?? "")
            .Where(build => build.Engine is "optiscaler" or "dll" && build.Available)
            .Select(build => new UpscalerBuildEntry
            {
                Id = build.Id,
                Family = build.Family,
                Version = build.Version,
                Channel = build.Channel,
                DownloadBytes = build.DownloadBytes,
                Models = build.Models.ToArray(),
                Supported = build.Supported,
            })
            .ToArray();
        var stored = store.Install(appId);
        var install = stored is not null ? InstallEntry(stored) : null;
        if (stored is not null && install?.Verdict is { } verdict && verdict != OptiScalerLog.NotRun)
        {
            try
            {
                store.SettleHistory(appId, stored.Install.Build, verdict, install.Observed);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.history", exception.GetType().Name);
            }
        }

        var history = store.History(appId)
            .Select(item => new UpscalerHistoryEntry
            {
                Build = item.Build,
                At = (long)item.At,
                Result = item.Result,
                Label = UpscalerLabel.Badge(data.Catalog.Build(item.Build), item.Model),
                Observed = item.Observed,
            })
            .ToArray();
        return new UpscalerGameDetail
        {
            History = history.Length > 0 ? history : null,
            Game = summary,
            Exe = analysis.Exe,
            Apis = analysis.Apis.ToArray(),
            Inputs = analysis.Inputs.Select(input => new UpscalerInput { Kind = input.Key, Files = input.Value.ToArray() }).ToArray(),
            AntiCheat = analysis.AntiCheat,
            Foreign = analysis.Foreign && analysis.ForeignIdentity is { } identity
                ? new UpscalerForeignSummary { Engine = identity.Engine, Variant = identity.Variant, ManifestError = identity.ManifestError }
                : null,
            Recipe = recipe is null
                ? null
                : new UpscalerRecipeStatus
                {
                    Status = recipe.Status,
                    Installable = recipe.Dependencies.Count == 0 && recipe.Configuration.Count == 0,
                    Revision = recipe.Revision,
                    RecommendedBuild = recipe.RecommendedBuild,
                    Dependencies = Dependencies(recipe),
                    Args = recipe.Args.Count > 0 ? recipe.Args.ToArray() : null,
                },
            Preferred = UpscalerPlanner.PreferredBuild(data.Catalog, generation, recipe?.RecommendedBuild),
            Builds = builds,
            Install = install is not null
                ? install
                : summary.State == UpscalerGameStates.PanelUnknown
                    ? new UpscalerInstallEntry { Proxy = "", Status = UpscalerGameStates.Installed }
                    : null,
        };
    }

    private UpscalersResponse BeginInstall(UpscalersRequest request)
    {
        var appId = request.AppId!;
        var build = data.Catalog.Build(request.Build!);
        if (build is null || !build.Available)
        {
            throw new UpscalerException("unknown_build");
        }

        if (build.Engine is not ("optiscaler" or "dll"))
        {
            throw new UpscalerException("engine_unsupported");
        }

        if (request.Quality is not null && !data.Catalog.QualityRatios.ContainsKey(request.Quality))
        {
            throw new UpscalerException("invalid_quality");
        }

        if (request.Model is not null && build.Models.All(model => model.Id != request.Model))
        {
            throw new UpscalerException("invalid_model");
        }

        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        var recipe = Recipe(app);
        if (build.Engine == "optiscaler" && recipe is not null && (recipe.Dependencies.Count > 0 || recipe.Configuration.Count > 0))
        {
            throw new UpscalerException("recipe_unsupported");
        }

        GameGuards.EnsureCanInstall(app, runningImages());
        var job = jobs.Begin("install", appId);
        if (request.Sharpness is not null && !data.Catalog.Sharpness.ContainsKey(request.Sharpness))
        {
            throw new UpscalerException("invalid_sharpness");
        }

        if (request.FrameGen == true && request.FrameGenRoute == "anr" && !UpscalerPlanner.AnrCapable(data.Catalog, build, Gpu.Generation))
        {
            throw new UpscalerException("anr_build");
        }

        var choice = new UpscalerChoice
        {
            Quality = request.Quality,
            Model = request.Model,
            Sharpness = request.Sharpness,
            FrameGen = request.FrameGen == true,
            FrameGenRoute = request.FrameGenRoute,
        };
        _ = start(() => RunInstallAsync(app, build.Id, choice, recipe));
        return Ok(job: job);
    }

    private UpscalersResponse BeginUninstall(string appId)
    {
        var app = steam.Find(appId);
        var stored = store.Install(appId) ?? FromManifest(app) ?? throw new UpscalerException("not_patched");
        if (app is not null)
        {
            GameGuards.EnsureClosed(app, runningImages());
        }

        var job = jobs.Begin("uninstall", appId);
        _ = start(() => RunUninstallAsync(appId, stored));
        return Ok(job: job);
    }

    private async Task RunInstallAsync(SteamApp app, string buildId, UpscalerChoice choice, GameRecipe? recipe)
    {
        var appId = app.AppId;
        Record(appId, "install", "started", buildId, null);
        try
        {
            jobs.Stage("prepare");
            var catalog = data.Catalog;
            var plan = catalog.Build(buildId)!;
            var assets = UpscalerPlanner.BuildAssets(catalog, plan);
            var total = assets.GroupBy(asset => asset.Sha256, StringComparer.Ordinal).Sum(group => group.Last().Size);
            var pending = assets.Any(asset => !cache.Ready(asset));
            jobs.Stage(pending ? "download" : "install", total);
            var progress = new Progress<long>(done =>
            {
                jobs.Progress(done);
                if (done >= total)
                {
                    jobs.Stage("install");
                }
            });
            var previous = store.Install(appId);
            var install = plan.Engine == "dll"
                ? await new DllInstaller(catalog, cache).InstallAsync(
                    buildId,
                    app.Root,
                    () => Analyze(app, recipe),
                    recipe?.LegacyFfxSwap ?? true,
                    previous?.Install,
                    false,
                    progress,
                    CancellationToken.None).ConfigureAwait(false)
                : await new OptiScalerInstaller(catalog, cache, Gpu.Generation).InstallAsync(
                    () => Analyze(app, recipe),
                    recipe,
                    new OptiScalerInstallRequest { Build = buildId, Choice = choice },
                    previous?.Install,
                    folder => store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, folder)),
                    progress,
                    CancellationToken.None).ConfigureAwait(false);
            install.AddedArgs = previous?.Install.AddedArgs ?? Array.Empty<string>();
            try
            {
                var installedAt = clock();
                store.SetInstall(appId, install, installedAt);
                WriteRecord(install, installedAt);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                OptiScalerInstaller.Uninstall(install);
                throw new UpscalerException("state_save_failed", exception.GetType().Name);
            }

            if (!ManifestCheck.Presence(install.Target).Installed)
            {
                store.ClearInstall(appId);
                throw new UpscalerException("install_unverified");
            }

            jobs.Stage("launch");
            await ApplyLaunchArgsAsync(appId, install).ConfigureAwait(false);
            try
            {
                store.AddHistory(appId, new UpscalerHistoryItem(clock(), install.Build, install.Proxy.Length > 0 ? install.Proxy : null,
                    install.Engine == "dll" ? "not_run" : "pending", install.Exe, install.Options.Model));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.history", exception.GetType().Name);
            }

            Record(appId, "install", "done", install.Build, null);
            jobs.Finish();
        }
        catch (Exception exception)
        {
            Fail(appId, "install", buildId, exception);
        }
    }

    private async Task RunUninstallAsync(string appId, StoredUpscaler stored)
    {
        Record(appId, "uninstall", "started", stored.Install.Build, null);
        try
        {
            jobs.Stage("restore");
            var kept = OptiScalerInstaller.Uninstall(stored.Install);
            if (ManifestCheck.Presence(stored.Install.Target).Present)
            {
                throw new UpscalerException("files_kept", kept.Count.ToString(System.Globalization.CultureInfo.InvariantCulture));
            }

            if (stored.Install.AddedArgs.Count > 0 && !await RevertLaunchArgsAsync(appId, stored.Install.AddedArgs).ConfigureAwait(false))
            {
                Record(appId, "launch", "error", stored.Install.Build, "launch_args_kept");
            }

            store.ClearInstall(appId);
            Record(appId, "uninstall", "done", stored.Install.Build, null);
            jobs.Finish();
        }
        catch (Exception exception)
        {
            Fail(appId, "uninstall", stored.Install.Build, exception);
        }
    }

    /// <summary>
    /// Puts the recipe's arguments in Steam's launch options, keeping whatever the user wrote, and remembers which ones
    /// Panel added. The install stands either way: without Steam's debugging port the game page says what to add by hand.
    /// </summary>
    private async Task ApplyLaunchArgsAsync(string appId, InstalledUpscaler install)
    {
        if ((install.Args.Count == 0 && install.AddedArgs.Count == 0) || launchOptions is null || !long.TryParse(appId, out var id))
        {
            return;
        }

        var read = await launchOptions.ReadAsync(id, CancellationToken.None).ConfigureAwait(false);
        if (!read.Succeeded)
        {
            log("upscalers.launch", $"{appId} read {read.Outcome} {read.Reason}");
            return;
        }

        var current = read.Value ?? "";
        var plan = LaunchOptionsComposer.Replace(current, install.AddedArgs, install.Args);
        if (plan is null)
        {
            log("upscalers.launch", $"{appId} ambiguous");
            return;
        }

        var installedAt = store.Install(appId)?.InstalledAt ?? clock();
        if (plan.Value != current)
        {
            var before = install.AddedArgs;
            // Saved before Steam is touched: if the companion dies mid-write, a later removal still takes them out.
            install.AddedArgs = before.Union(plan.Added, StringComparer.Ordinal).ToList();
            store.SetInstall(appId, install, installedAt);
            var written = await launchOptions.WriteAsync(id, plan.Value, false, CancellationToken.None).ConfigureAwait(false);
            if (written.Outcome != SteamLaunchOptionsOutcome.Written)
            {
                log("upscalers.launch", $"{appId} write {written.Outcome} {written.Reason}");
                install.AddedArgs = before;
                store.SetInstall(appId, install, installedAt);
                return;
            }
        }

        install.AddedArgs = plan.Added;
        store.SetInstall(appId, install, installedAt);
        WriteRecord(install, installedAt);
    }

    private async Task<bool> RevertLaunchArgsAsync(string appId, IReadOnlyList<string> added)
    {
        if (launchOptions is null || !long.TryParse(appId, out var id))
        {
            return false;
        }

        var read = await launchOptions.ReadAsync(id, CancellationToken.None).ConfigureAwait(false);
        var current = read.Value ?? "";
        if (!read.Succeeded || LaunchOptionsComposer.Revert(current, added) is not { } value)
        {
            return false;
        }

        return value == current
            || (await launchOptions.WriteAsync(id, value, false, CancellationToken.None).ConfigureAwait(false)).Outcome == SteamLaunchOptionsOutcome.Written;
    }

    private UpscalerDependencyStatus[]? Dependencies(GameRecipe recipe)
    {
        if (recipe.Dependencies.Count == 0 || data.Recipes is null)
        {
            return null;
        }

        var plan = RecipeDependencyPlan.Build(data.Recipes, recipe, component => component == "vc14_x64" ? vcRuntime() : null);
        var entries = plan.Entries
            .Where(entry => entry.Outcome != DependencyOutcome.NotApplicable)
            .Select(entry => new UpscalerDependencyStatus
            {
                Id = entry.Id,
                Kind = entry.Kind,
                State = entry.Outcome switch
                {
                    DependencyOutcome.InstallFromAsset => "install",
                    DependencyOutcome.RedistSatisfied => "satisfied",
                    DependencyOutcome.RedistMissing => "missing",
                    DependencyOutcome.RedistOutdated => "outdated",
                    _ => "user_file",
                },
                Name = entry.Name,
                Installed = entry.InstalledVersion,
                Required = entry.RequiredVersion,
                Url = entry.Url,
            })
            .ToArray();
        return entries.Length > 0 ? entries : null;
    }

    private void Fail(string appId, string action, string build, Exception exception)
    {
        string code;
        string? detail = null;
        switch (exception)
        {
            case UpscalerException upscaler:
                code = upscaler.Code;
                detail = upscaler.Detail.Length > 0 ? upscaler.Detail : null;
                break;
            case AssetException asset:
                code = asset.Code;
                detail = asset.Detail.Length > 0 ? asset.Detail : null;
                break;
            case OperationCanceledException:
                code = "cancelled";
                break;
            default:
                code = "internal_error";
                log($"upscalers.{action}", exception.ToString());
                break;
        }

        log($"upscalers.{action}", $"{appId} {build} {code} {detail}");
        jobs.Fail(code, detail);
        try
        {
            Record(appId, action, "error", build, code);
        }
        catch (Exception recordFailure) when (recordFailure is IOException or UnauthorizedAccessException)
        {
            log("upscalers.journal", recordFailure.GetType().Name);
        }
    }

    private void Record(string appId, string action, string state, string? build, string? error)
    {
        try
        {
            store.Record(new UpscalerAction(clock(), appId, action, state, build, error));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.journal", exception.GetType().Name);
        }
    }

    private void WriteRecord(InstalledUpscaler install, double installedAt)
    {
        try
        {
            PanelInstallRecord.Write(install.Target, new StoredUpscaler(install, installedAt));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.record", exception.GetType().Name);
        }
    }

    /// <summary>
    /// A game whose Panel state was lost (the package was reinstalled) but whose folder still holds a complete Panel
    /// manifest: adopted from the record beside it, or reported as Panel's with an unknown build. Null when nothing is there.
    /// </summary>
    private string? Recover(SteamApp app, GameAnalysis analysis)
    {
        var target = analysis.Target;
        if (target is null || store.Install(app.AppId) is not null || ManifestOf(target) is null
            || store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, target)))
        {
            return null;
        }

        if (PanelInstallRecord.Read(target) is { } record && SamePath(record.Install.Target, target))
        {
            try
            {
                store.SetInstall(app.AppId, record.Install, record.InstalledAt);
                log("upscalers.recovered", app.AppId);
                return UpscalerGameStates.Installed;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                log("upscalers.recover", exception.GetType().Name);
            }
        }

        return UpscalerGameStates.PanelUnknown;
    }

    private static GameManifest? ManifestOf(string target) =>
        GameFiles.ReadManifest(target) is { Incomplete: false } manifest && manifest.Engine != "dll" ? manifest : null;

    private StoredUpscaler? FromManifest(SteamApp? app)
    {
        if (app is null || Scan(app, null).Target is not { } target || ManifestOf(target) is null)
        {
            return null;
        }

        return new StoredUpscaler(new InstalledUpscaler { Target = target }, 0);
    }

    private static UpscalerGameSummary WithState(UpscalerGameSummary row, string state)
    {
        row.State = state;
        return row;
    }

    private UpscalerGameSummary Summary(SteamApp app, IReadOnlyList<string>? images)
    {
        var row = new UpscalerGameSummary
        {
            AppId = app.AppId,
            Name = app.Name,
            Updating = app.UpdateState is not null,
            Running = images is null ? null : GameGuards.IsRunningUnder(app.Root, images),
        };
        if (store.Install(app.AppId) is { } stored)
        {
            row.State = ManifestCheck.Presence(stored.Install.Target).Installed ? UpscalerGameStates.Installed : UpscalerGameStates.Missing;
            row.Build = stored.Install.Build;
            row.Version = data.Catalog.Build(stored.Install.Build)?.Version;
            row.Label = UpscalerLabel.Badge(data.Catalog.Build(stored.Install.Build), stored.Install.Options.Model);
        }

        return row;
    }

    private UpscalerInstallEntry InstallEntry(StoredUpscaler stored)
    {
        var install = stored.Install;
        var verdict = UpscalerVerdict.Read(install, stored.InstalledAt);
        return new UpscalerInstallEntry
        {
            Verdict = verdict?.Verdict,
            Observed = verdict?.Observed,
            Provider = verdict?.Provider,
            Fallback = verdict?.Fallback,
            Build = install.Build,
            Version = data.Catalog.Build(install.Build)?.Version,
            Proxy = install.Proxy,
            Exe = install.Exe,
            Quality = install.Options.Quality,
            Model = install.Options.Model,
            InstalledAt = (long)stored.InstalledAt,
            Status = ManifestCheck.Presence(install.Target).Installed ? UpscalerGameStates.Installed : UpscalerGameStates.Missing,
            Label = UpscalerLabel.Badge(data.Catalog.Build(install.Build), install.Options.Model),
            AddedArgs = install.AddedArgs.Count > 0 ? install.AddedArgs.ToArray() : null,
            MissingArgs = install.Args.Except(install.AddedArgs, StringComparer.Ordinal).ToArray() is { Length: > 0 } missing ? missing : null,
        };
    }

    private static readonly TimeSpan MissingCoverMemory = TimeSpan.FromSeconds(60);
    private const int MaximumCachedCovers = 512;

    /// <summary>The game's cached artwork shrunk to a list thumbnail, kept in memory; null when Steam has none.</summary>
    public UpscalerCover? Cover(string appId)
    {
        var now = clock();
        lock (coverLock)
        {
            if (covers.TryGetValue(appId, out var known) && (known.Cover is not null || known.Until > now))
            {
                return known.Cover;
            }
        }

        UpscalerCover? cover = null;
        if (CoverFiles.Find(fileSystem, steam.Roots(), appId) is { } source && scaleCover(source, UpscalersWireCodec.MaximumCoverWidth) is { } scaled)
        {
            cover = new UpscalerCover { Mime = scaled.Mime, Data = Convert.ToBase64String(scaled.Data) };
        }

        lock (coverLock)
        {
            if (covers.Count >= MaximumCachedCovers)
            {
                covers.Clear();
            }

            covers[appId] = (now + MissingCoverMemory.TotalSeconds, cover);
        }

        return cover;
    }

    private GameRecipe? Recipe(SteamApp app) => data.Recipes?.Match(app.AppId, "optiscaler", Platform, Arch, app.BuildId);

    private GameAnalysis Analyze(SteamApp app, GameRecipe? recipe) => GameFolder.Analyze(fileSystem, app.Root, null, recipe?.Exe);

    // The scan reads executables: it is kept per game until the folder or Steam's state changes.
    private GameAnalysis Scan(SteamApp app, GameRecipe? recipe, bool force = false)
    {
        var stamp = Stamp(app);
        lock (scanLock)
        {
            if (!force && scans.TryGetValue(app.AppId, out var cached) && cached.Stamp == stamp)
            {
                return cached.Analysis;
            }
        }

        var analysis = Analyze(app, recipe ?? Recipe(app));
        lock (scanLock)
        {
            scans[app.AppId] = (stamp, analysis);
        }

        return analysis;
    }

    private static long Stamp(SteamApp app)
    {
        try
        {
            return Directory.GetLastWriteTimeUtc(app.Root).Ticks ^ app.StateFlags;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return 0;
        }
    }

    private static bool SamePath(string? left, string right) =>
        left is not null && string.Equals(
            left.Replace('/', '\\').TrimEnd('\\'),
            right.Replace('/', '\\').TrimEnd('\\'),
            StringComparison.OrdinalIgnoreCase);

    private UpscalersResponse Ok(UpscalersOverview? overview = null, UpscalerGameDetail? game = null, UpscalerJobStatus? job = null, UpscalerCover? cover = null) =>
        new() { Status = UpscalersResponseStatus.Ok, Overview = overview, Game = game, Job = job ?? jobs.Snapshot(), Cover = cover };
}
