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
public sealed partial class UpscalerService : IUpscalersController
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
    private int retrying;
    private readonly Func<string?> vcRuntime;
    private readonly HelixSr? helix;
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
        Func<string?>? vcRuntime = null,
        HelixSr? helix = null)
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
        this.helix = helix;
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
                case UpscalersOperation.Ini:
                    return await Task.Run(() => IniSchema(request.AppId!), cancellationToken).ConfigureAwait(false);
                case UpscalersOperation.Image:
                    return await Task.Run(() => ImageSettingsOf(request.AppId!), cancellationToken).ConfigureAwait(false);
                case UpscalersOperation.Configure or UpscalersOperation.SetIni or UpscalersOperation.SetImage or UpscalersOperation.RestoreImage:
                    if (!request.ExperimentalEnabled)
                    {
                        return UpscalersResponse.Rejected("experimental_required", jobs.Snapshot());
                    }

                    return await Task.Run(() => request.Operation switch
                    {
                        UpscalersOperation.Configure => Configure(request),
                        UpscalersOperation.SetIni => SetIni(request.AppId!, request.Key!, request.Value!),
                        UpscalersOperation.SetImage => SetImage(request),
                        _ => RestoreImage(request.AppId!),
                    }, cancellationToken).ConfigureAwait(false);
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
        if (launchOptions is not null && store.AppsWithStrandedArgs.Count > 0 && Interlocked.CompareExchange(ref retrying, 1, 0) == 0)
        {
            _ = Task.Run(async () =>
            {
                try
                {
                    await RetryStrandedArgsAsync().ConfigureAwait(false);
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    log("upscalers.launch", exception.GetType().Name);
                }
                finally
                {
                    Interlocked.Exchange(ref retrying, 0);
                }
            });
        }

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
            .Where(build => build.Available && (build.Engine == "optiscaler"
                || (build.Engine == "helixsr" && OffersHelix(analysis))
                || (build.Engine == "dll" && data.Catalog.Build(build.Id) is { } dll
                    && UpscalerPlanner.SupportsDllTargets(dll, DllInstaller.Targets(analysis, Resolved(app, "dll")?.LegacyFfxSwap ?? true)))))
            .Select(build => new UpscalerBuildEntry
            {
                Id = build.Id,
                Family = build.Family,
                Version = build.Version,
                Channel = build.Channel,
                DownloadBytes = build.DownloadBytes + PlatformBytes(build.Id),
                Models = build.Models.ToArray(),
                Supported = build.Supported,
                Engine = build.Engine is "dll" or "helixsr" ? build.Engine : null,
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
                    Installable = AutomaticRecipe.Installable(data.Recipes, recipe),
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

        if (build.Engine is not ("optiscaler" or "dll") && !(build.Engine == "helixsr" && helix is not null))
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

        if (request.Sharpness is not null && !data.Catalog.Sharpness.ContainsKey(request.Sharpness))
        {
            throw new UpscalerException("invalid_sharpness");
        }

        if (request.FrameGen == true && request.FrameGenRoute == "anr" && !UpscalerPlanner.AnrCapable(data.Catalog, build, Gpu.Generation))
        {
            throw new UpscalerException("anr_build");
        }

        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        var recipe = Recipe(app);
        var automatic = build.Engine == "optiscaler" ? AutomaticRecipe.Plan(data.Recipes, recipe) : null;
        var resolved = Resolved(app, build.Engine);
        if (build.Engine == "helixsr" && !OffersHelix(Scan(app, recipe)))
        {
            throw new UpscalerException("helixsr_no_fsr");
        }

        // Everything that can refuse the request runs before the job starts: a job is only ever left by Finish or Fail.
        GameGuards.EnsureCanInstall(app, runningImages());
        var job = jobs.Begin("install", appId);

        var choice = new UpscalerChoice
        {
            Quality = request.Quality,
            Model = request.Model,
            Sharpness = request.Sharpness,
            FrameGen = request.FrameGen == true,
            FrameGenRoute = request.FrameGenRoute,
        };
        _ = start(() => RunInstallAsync(app, build.Id, choice, resolved, automatic));
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

    private async Task RunInstallAsync(SteamApp app, string buildId, UpscalerChoice choice, ResolvedRecipe? recipe, AutomaticRecipe? automatic)
    {
        var appId = app.AppId;
        Record(appId, "install", "started", buildId, null);
        try
        {
            jobs.Stage("prepare");
            var catalog = data.Catalog;
            var plan = catalog.Build(buildId)!;
            var previous = store.Install(appId);
            if (previous?.Install.Engine == "helixsr" && plan.Engine != "helixsr")
            {
                // HelixSR comes out before the switch; the arguments Panel added stay recorded so the new install or a later removal takes them out.
                await RemoveInstallAsync(app.Root, previous.Install).ConfigureAwait(false);
                if (previous.Install.AddedArgs.Count > 0)
                {
                    store.SetStrandedArgs(appId, previous.Install.AddedArgs.Union(store.StrandedArgs(appId), StringComparer.Ordinal).ToList());
                }

                store.ClearInstall(appId);
                previous = null;
            }

            var install = plan.Engine == "helixsr"
                ? await InstallHelixAsync(app, plan, choice, recipe, previous?.Install).ConfigureAwait(false)
                : await InstallOptiScalerAsync(app, plan, choice, recipe, automatic, previous?.Install).ConfigureAwait(false);
            install.AddedArgs = previous?.Install.AddedArgs ?? Array.Empty<string>();
            try
            {
                var installedAt = clock();
                store.SetInstall(appId, install, installedAt);
                if (install.Engine == "optiscaler")
                {
                    store.SetImageReceipt(appId, install.ImageReceipt);
                }

                WriteRecord(install, installedAt);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                await RemoveInstallAsync(app.Root, install).ConfigureAwait(false);
                throw new UpscalerException("state_save_failed", exception.GetType().Name);
            }

            if (!IsInstalled(install))
            {
                if (install.Engine == "helixsr")
                {
                    try
                    {
                        await RemoveInstallAsync(app.Root, install).ConfigureAwait(false);
                    }
                    catch (Exception removal) when (removal is UpscalerException or IOException or UnauthorizedAccessException)
                    {
                        log("upscalers.helix", "removal after an unverified install: " + removal.GetType().Name);
                    }
                }

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

    private async Task<InstalledUpscaler> InstallOptiScalerAsync(SteamApp app, UpscalerBuild plan, UpscalerChoice choice, ResolvedRecipe? recipe, AutomaticRecipe? automatic, InstalledUpscaler? previous)
    {
        var catalog = data.Catalog;
        var buildId = plan.Id;
        var assets = UpscalerPlanner.BuildAssets(catalog, plan).Concat(automatic?.Assets() ?? Array.Empty<UpscalerAsset>()).ToList();
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
        return plan.Engine == "dll"
            ? await new DllInstaller(catalog, cache).InstallAsync(
                buildId,
                app.Root,
                () => Analyze(app, recipe?.Exe),
                recipe?.LegacyFfxSwap ?? true,
                previous,
                false,
                progress,
                CancellationToken.None,
                folder => store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, folder))).ConfigureAwait(false)
            : await new OptiScalerInstaller(catalog, cache, Gpu.Generation).InstallAsync(
                () => Analyze(app, recipe?.Exe),
                recipe,
                new OptiScalerInstallRequest { Build = buildId, Choice = choice },
                previous,
                folder => store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, folder)),
                progress,
                CancellationToken.None,
                automatic).ConfigureAwait(false);
    }

    private async Task RunUninstallAsync(string appId, StoredUpscaler stored)
    {
        Record(appId, "uninstall", "started", stored.Install.Build, null);
        try
        {
            jobs.Stage("restore");
            var kept = await RemoveInstallAsync(steam.Find(appId)?.Root, stored.Install).ConfigureAwait(false);
            if (stored.Install.Engine == "helixsr" ? HelixSr.HasMarker(stored.Install.Target) : ManifestCheck.Presence(stored.Install.Target).Present)
            {
                throw new UpscalerException("files_kept", kept.Count.ToString(System.Globalization.CultureInfo.InvariantCulture));
            }

            var added = stored.Install.AddedArgs.Union(store.StrandedArgs(appId), StringComparer.Ordinal).ToList();
            if (added.Count > 0 && !await RevertLaunchArgsAsync(appId, added).ConfigureAwait(false))
            {
                // Kept apart from the install so a later look at the game, or the next install, still takes them out.
                store.SetStrandedArgs(appId, added);
                Record(appId, "launch", "error", stored.Install.Build, "launch_args_kept");
            }
            else if (added.Count > 0)
            {
                store.SetStrandedArgs(appId, Array.Empty<string>());
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
        var stranded = store.StrandedArgs(appId);
        if (stranded.Count > 0)
        {
            install.AddedArgs = install.AddedArgs.Union(stranded, StringComparer.Ordinal).ToList();
        }

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
                // Unconfirmed may still have reached Steam: the union stays recorded so removal can take it out.
                log("upscalers.launch", $"{appId} write {written.Outcome} {written.Reason}");
                return;
            }
        }

        install.AddedArgs = plan.Added;
        store.SetInstall(appId, install, installedAt);
        if (stranded.Count > 0)
        {
            store.SetStrandedArgs(appId, Array.Empty<string>());
        }

        WriteRecord(install, installedAt);
    }

    /// <summary>Takes out arguments a removal left in Steam, once Steam can be reached again.</summary>
    private async Task RetryStrandedArgsAsync()
    {
        foreach (var appId in store.AppsWithStrandedArgs)
        {
            if (store.Install(appId) is not null || jobs.Snapshot()?.State == UpscalerJobStates.Running)
            {
                continue;
            }

            var stranded = store.StrandedArgs(appId);
            if (await RevertLaunchArgsAsync(appId, stranded).ConfigureAwait(false))
            {
                store.SetStrandedArgs(appId, Array.Empty<string>());
                log("upscalers.launch", $"{appId} stranded args removed");
            }
        }
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
            var owner = store.InstalledAppIds.FirstOrDefault(id => SamePath(store.Install(id)?.Install.Target, install.Target));
            var receipt = owner is null ? null : store.ImageReceipt(owner);
            PanelInstallRecord.Write(install.Target, new StoredUpscaler(install, installedAt),
                receipt is not null && SamePath(Path.GetDirectoryName(receipt.Target), install.Target) ? receipt : null);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.record", exception.GetType().Name);
        }
    }

    private bool OffersHelix(GameAnalysis analysis) => helix is not null && analysis.Inputs.Any(input => input.Key == "fsr31");

    private long PlatformBytes(string buildId) =>
        data.Catalog.Build(buildId) is { Available: true } build
            ? build.AssetsFor(Platform).Select(id => data.Catalog.Asset(id)!).GroupBy(asset => asset.Sha256, StringComparer.Ordinal).Sum(group => group.Last().Size)
            : 0;

    /// <summary>HelixSR's record and marker are what say it is in the game; every other engine has its manifest.</summary>
    private static bool IsInstalled(InstalledUpscaler install) =>
        install.Engine == "helixsr"
            ? HelixSr.HasMarker(install.Target) && install.HelixFile.Length > 0 && File.Exists(install.HelixFile)
            : ManifestCheck.Presence(install.Target).Installed;

    private async Task<InstalledUpscaler> InstallHelixAsync(SteamApp app, UpscalerBuild build, UpscalerChoice choice, ResolvedRecipe? recipe, InstalledUpscaler? previous)
    {
        var runner = helix ?? throw new UpscalerException("engine_unsupported");
        var analysis = Analyze(app, recipe?.Exe);
        var target = analysis.Target ?? throw new UpscalerException("no_exe");
        if (analysis.AntiCheat)
        {
            throw new UpscalerException("anti_cheat");
        }

        if (!OffersHelix(analysis))
        {
            throw new UpscalerException("helixsr_no_fsr");
        }

        await EnsureHelixAsync(runner, build).ConfigureAwait(false);
        GameFiles.RecoverOrphan(target, folder => store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, folder)));
        if (previous is not null)
        {
            await RemoveInstallAsync(app.Root, previous).ConfigureAwait(false);
            store.ClearInstall(app.AppId);
            if (previous.AddedArgs.Count > 0)
            {
                store.SetStrandedArgs(app.AppId, previous.AddedArgs.Union(store.StrandedArgs(app.AppId), StringComparer.Ordinal).ToList());
            }

            GameFiles.RecoverOrphan(target, _ => false);
            analysis = Analyze(app, recipe?.Exe);
            target = analysis.Target ?? throw new UpscalerException("no_exe");
        }

        if (analysis.Foreign)
        {
            throw new UpscalerException("foreign");
        }

        jobs.Stage("install");
        HelixGame game;
        try
        {
            game = await runner.InstallAsync(app.Root, CancellationToken.None).ConfigureAwait(false);
        }
        catch (UpscalerException)
        {
            await UndoHelixAsync(runner, app.Root, target).ConfigureAwait(false);
            throw;
        }

        var exeFolder = game.ExeFolder ?? target;
        var log = game.LogPath ?? Path.Combine(exeFolder, "helixsr.log");
        try
        {
            HelixSr.WriteMarker(target, build.Way, runner.ReleaseName);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or UpscalerException)
        {
            await UndoHelixAsync(runner, app.Root, target).ConfigureAwait(false);
            throw exception is UpscalerException known ? known : new UpscalerException("state_save_failed", exception.GetType().Name);
        }

        var archive = data.Catalog.Asset(build.Archive)!;
        return new InstalledUpscaler
        {
            Build = build.Id,
            Archive = build.Archive,
            Engine = "helixsr",
            Way = build.Way,
            Target = target,
            Exe = analysis.Exe,
            ExeFolder = exeFolder,
            Log = log,
            HelixFile = Path.Combine(Path.GetDirectoryName(log) ?? exeFolder, HelixRestore.Record),
            Options = new UpscalerChoice { Quality = choice.Quality, Sharpness = choice.Sharpness, Model = choice.Model },
            Components = new[] { new KeyValuePair<string, string>(archive.Id, runner.Digest ?? archive.Sha256) },
        };
    }

    /// <summary>A failed install may have swapped DLLs before it failed: the bridge takes them out, else the recorded swaps are undone by hand.</summary>
    private async Task UndoHelixAsync(HelixSr runner, string root, string folder)
    {
        try
        {
            await runner.RemoveAsync(root, CancellationToken.None).ConfigureAwait(false);
            return;
        }
        catch (UpscalerException)
        {
        }

        try
        {
            HelixRestore.ByHand(folder);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.helix", "undo after a failed install: " + exception.GetType().Name);
        }
    }

    /// <summary>Python first, then HelixSR's release: each is downloaded and unpacked once and kept until the catalog pins another.</summary>
    private async Task EnsureHelixAsync(HelixSr runner, UpscalerBuild build)
    {
        var catalog = data.Catalog;
        foreach (var python in build.AssetsFor(Platform).Select(id => catalog.Asset(id)!))
        {
            if (runner.PythonIs(python.Sha256))
            {
                continue;
            }

            jobs.Stage(HelixSr.PythonStage, python.Size);
            var file = await cache.EnsureAsync(python, new Progress<long>(jobs.Progress), CancellationToken.None).ConfigureAwait(false);
            runner.UnpackPython(file, python.Sha256);
            Discard(python);
        }

        var pinned = catalog.Asset(build.Archive)!;
        if (runner.ReleaseReady && (runner.Digest ?? pinned.Sha256) == pinned.Sha256)
        {
            return;
        }

        jobs.Stage("download", pinned.Size);
        var archive = await cache.EnsureAsync(pinned, new Progress<long>(jobs.Progress), CancellationToken.None).ConfigureAwait(false);
        jobs.Stage(HelixSr.UnpackStage);
        runner.UnpackRelease(archive, pinned.Sha256);
        Discard(pinned);
    }

    /// <summary>The downloaded archive is only a means to the unpacked folder; its copy in the cache goes.</summary>
    private void Discard(UpscalerAsset asset)
    {
        try
        {
            var folder = Path.GetDirectoryName(cache.FilePath(asset));
            if (folder is not null && Directory.Exists(folder))
            {
                Directory.Delete(folder, true);
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.cache", exception.GetType().Name);
        }
    }

    private async Task<IReadOnlyList<string>> RemoveInstallAsync(string? root, InstalledUpscaler install)
    {
        if (install.Engine != "helixsr")
        {
            return OptiScalerInstaller.Uninstall(install);
        }

        await RemoveHelixAsync(root, install).ConfigureAwait(false);
        return Array.Empty<string>();
    }

    /// <summary>The bridge decides; when its DLL is already gone, or HelixSR cannot run, the recorded swaps are undone by hand.</summary>
    private async Task RemoveHelixAsync(string? root, InstalledUpscaler install)
    {
        var runner = helix;
        var record = install.HelixFile;
        var recorded = record.Length > 0 && File.Exists(record);
        var bridge = runner is { Ready: true } && root is not null;
        if (!recorded)
        {
            if (!bridge)
            {
                throw new UpscalerException("helixsr_missing");
            }

            try
            {
                await runner!.RemoveAsync(root!, CancellationToken.None).ConfigureAwait(false);
            }
            catch (UpscalerException error) when (HelixBridge.NotInstalled(error.Detail))
            {
            }

            log("upscalers.helix", "record_missing");
        }
        else if (bridge)
        {
            try
            {
                await runner!.RemoveAsync(root!, CancellationToken.None).ConfigureAwait(false);
            }
            catch (UpscalerException error) when (HelixBridge.NotInstalled(error.Detail))
            {
                RestoreHelixByHand(Path.GetDirectoryName(record)!, "bridge_not_installed");
            }
        }
        else
        {
            RestoreHelixByHand(Path.GetDirectoryName(record)!, "release_missing");
        }

        GameConfigFiles.Restore(install.GameConfig);
        foreach (var generated in new[] { install.Log, install.Log.Length > 0 ? Path.Combine(Path.GetDirectoryName(install.Log) ?? "", HelixLog.FileName) : "" })
        {
            DeleteFile(generated);
        }

        var meta = Path.Combine(install.Target, GameManifest.Folder);
        if (Directory.Exists(meta) && (File.GetAttributes(meta) & FileAttributes.ReparsePoint) == 0)
        {
            Directory.Delete(meta, true);
        }
    }

    private void RestoreHelixByHand(string folder, string reason)
    {
        if (!HelixRestore.ByHand(folder))
        {
            log("upscalers.helix", "removal by hand left a HelixSR DLL with no backup (" + reason + ")");
            throw new UpscalerException(HelixBridge.FailedCode, "HelixSR's DLL has no backup of the game's file");
        }

        log("upscalers.helix", "taken out without its bridge (" + reason + ")");
    }

    private static void DeleteFile(string path)
    {
        if (path.Length == 0 || !File.Exists(path))
        {
            return;
        }

        var attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.ReadOnly) != 0)
        {
            File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
        }

        File.Delete(path);
    }

    /// <summary>
    /// A game whose Panel state was lost (the package was reinstalled) but whose folder still holds a complete Panel
    /// manifest: adopted from the record beside it, or reported as Panel's with an unknown build. Null when nothing is there.
    /// </summary>
    private string? Recover(SteamApp app, GameAnalysis analysis)
    {
        var target = PanelFolder(app, analysis);
        if (target is null || store.Install(app.AppId) is not null
            || store.InstalledAppIds.Any(other => SamePath(store.Install(other)?.Install.Target, target)))
        {
            return null;
        }

        if (PanelInstallRecord.Read(target) is { } record && SamePath(record.Install.Target, target))
        {
            try
            {
                store.SetInstall(app.AppId, record.Install, record.InstalledAt);
                if (PanelInstallRecord.ReadReceipt(target) is { } receipt)
                {
                    store.SetImageReceipt(app.AppId, receipt);
                }

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

    /// <summary>Where a complete Panel manifest sits in this game: OptiScaler beside the exe, the DLL mode at the root.</summary>
    private static string? PanelFolder(SteamApp app, GameAnalysis analysis)
    {
        if (analysis.Target is { } target && (ManifestOf(target) is not null || HelixSr.HasMarker(target)))
        {
            return target;
        }

        return GameFiles.ReadManifest(app.Root) is { Incomplete: false, Engine: "dll" } ? app.Root : null;
    }

    private StoredUpscaler? FromManifest(SteamApp? app)
    {
        if (app is null || PanelFolder(app, Scan(app, null)) is not { } target)
        {
            return null;
        }

        var engine = HelixSr.HasMarker(target) ? "helixsr" : GameFiles.ReadManifest(target)?.Engine ?? "optiscaler";
        return new StoredUpscaler(new InstalledUpscaler { Target = target, Engine = engine }, 0);
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
            row.State = IsInstalled(stored.Install) ? UpscalerGameStates.Installed : UpscalerGameStates.Missing;
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
            Sharpness = install.Options.Sharpness,
            FrameGen = install.Options.FrameGen ? true : null,
            FrameGenRoute = install.Options.FrameGenRoute,
            Engine = install.Engine,
            Anr = install.Anr ? true : null,
            Proxy = install.Proxy,
            Exe = install.Exe,
            Quality = install.Options.Quality,
            Model = install.Options.Model,
            InstalledAt = (long)stored.InstalledAt,
            Status = IsInstalled(install) ? UpscalerGameStates.Installed : UpscalerGameStates.Missing,
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

    private ResolvedRecipe? Resolved(SteamApp app, string engine) =>
        data.Resolver.Resolve(app.AppId, engine, Platform, Arch, app.BuildId, fileSystem, app.Root);

    private GameAnalysis Analyze(SteamApp app, string? exe) => GameFolder.Analyze(fileSystem, app.Root, null, exe);

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

        var analysis = Analyze(app, (recipe ?? Recipe(app))?.Exe);
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

    private UpscalersResponse Ok(UpscalersOverview? overview = null, UpscalerGameDetail? game = null, UpscalerJobStatus? job = null, UpscalerCover? cover = null,
        UpscalerOptions? options = null, UpscalerIniSection[]? ini = null, UpscalerImageSettings? image = null, UpscalerIniEdit? iniEdit = null) =>
        new()
        {
            Status = UpscalersResponseStatus.Ok, Overview = overview, Game = game, Job = job ?? jobs.Snapshot(), Cover = cover,
            Options = options, Ini = ini, Image = image, IniEdit = iniEdit,
        };
}
