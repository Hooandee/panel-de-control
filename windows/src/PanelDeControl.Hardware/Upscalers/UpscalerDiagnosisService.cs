using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// The support report of one game (Linux's <c>diagnose</c>), the list of what each game ships (<c>compatibility</c>) and the
/// record of what Panel last wrote into OptiScaler.ini (<c>_wrote_ini</c>).
/// </summary>
public sealed partial class UpscalerService
{
    private const int LogExcerptLines = UpscalerDiagnosis.MaximumExcerpt;

    private static readonly Regex Noteworthy = new(
        @"\[(?:W|E|C)\]|Creating new|FSR4|Fsr4|FrameGen|FG |XeFG|Nukem|OptiFG|working as|Adapter Desc|custom|dlssg",
        RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex SkippedLine = new(
        @"VulkanSpoofing|freely downloadable|GitHub :|Nexus  :|paid for these|MULTIPLAYER|-{10}",
        RegexOptions.CultureInvariant);

    private static readonly Regex UserHome = new(
        @"(?:[A-Za-z]:)?[\\/](?:home|users)[\\/][^\\/\r\n:<>""']{1,64}",
        RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

    private static readonly Regex ComponentTag = new(@"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}\z", RegexOptions.CultureInvariant);

    private static readonly string[] LoaderFiles =
    {
        "dxgi.dll", "d3d11.dll", "d3d12.dll", "dinput8.dll", "version.dll", "winmm.dll", "winhttp.dll", "dbghelp.dll", "nvngx.dll",
        "OptiScaler.dll", "OptiScaler.ini", "ReShade.ini", "ReShade64.dll", "re2_fw_config.txt", "helixsr-install.json", "amd_fidelityfx_dx12.dll",
    };

    private static readonly string[] LoaderFolders = { "reframework", "OptiScaler", "Luma", "D3D12_Optiscaler", "plugins" };

    private static readonly string[] StoreFiles =
    {
        "steam_emu.ini", "steam_settings", "ColdClientLoader.ini", "OnlineFix.ini", "OnlineFix64.dll", "cream_api.ini", "SmartSteamEmu.ini", "CODEX.ini",
        "steam_interfaces.txt",
    };

    private static readonly HashSet<string> RoutineActions = new(StringComparer.Ordinal) { "refresh_wiki", "verify" };

    private UpscalersResponse Diagnose(string appId)
    {
        var app = steam.Find(appId);
        var stored = store.Install(appId);
        var report = new UpscalerDiagnosis
        {
            AppId = appId,
            Name = app?.Name,
            StateFlags = app?.StateFlags,
            BuildId = app?.BuildId,
            ManualExeSelected = store.Exe(appId) is not null,
            SteamLookup = new UpscalerDiagnosisSteam { Libraries = steam.Libraries().Count, Found = app is not null },
            Actions = store.Actions(appId)
                .Where(action => !RoutineActions.Contains(action.Action))
                .TakeLast(UpscalerDiagnosis.MaximumActions)
                .Select(action => new UpscalerDiagnosisAction
                {
                    At = (long)action.At,
                    Action = action.Action,
                    State = action.State,
                    Build = action.Build,
                    Error = action.Error,
                })
                .ToArray(),
            History = store.History(appId)
                .TakeLast(UpscalerDiagnosis.MaximumHistory)
                .Select(item => new UpscalerDiagnosisHistory
                {
                    Build = item.Build,
                    Proxy = item.Proxy,
                    At = (long)item.At,
                    Result = item.Result,
                    Observed = item.Observed,
                })
                .ToArray(),
            ImageSettings = UpscalerImageSettings.From(ImageState(appId)),
        };

        GameRecipe? recipe = null;
        GameAnalysis? analysis = null;
        if (app is not null)
        {
            recipe = Recipe(app);
            analysis = Scan(app, recipe);
            report.Foreign = analysis.Foreign && analysis.ForeignIdentity is { } identity
                ? new UpscalerForeignSummary { Engine = identity.Engine, Variant = identity.Variant, ManifestError = identity.ManifestError }
                : null;
            var blocked = Automatic(recipe) is (null, true);
            report.Recipe = recipe is null
                ? null
                : new UpscalerDiagnosisRecipe
                {
                    AppId = recipe.AppId,
                    Status = recipe.Status,
                    Revision = recipe.Revision,
                    Installable = AutomaticRecipe.Installable(data.Recipes, recipe),
                    Blocked = blocked ? true : null,
                    Dependencies = recipe.Dependencies.Count > 0 ? recipe.Dependencies.Take(16).ToArray() : null,
                    RequiredArgs = recipe.Args.Count > 0 ? recipe.Args.Take(16).ToArray() : null,
                };
            if (userMods.Status(appId) is { } mod)
            {
                report.Mod = new UpscalerDiagnosisMod { Count = mod.Count, Applied = stored?.Install.Mod is { } applied && applied.Value == mod.Id };
            }
        }

        if (stored is not null)
        {
            ReportInstall(report, stored, app);
        }

        if (app is not null && analysis is not null)
        {
            report.GameFiles = GameFilesReport(app, analysis, stored?.Install.Target);
            if (stored is { Install.Engine: "optiscaler" } && data.Catalog.Build(stored.Install.Build) is { } build)
            {
                report.CurrentSolution = CurrentSolution(app, analysis, build);
            }
        }

        return Ok(diagnosis: report);
    }

    private void ReportInstall(UpscalerDiagnosis report, StoredUpscaler stored, SteamApp? app)
    {
        var install = stored.Install;
        var options = install.Options;
        report.Install = new UpscalerDiagnosisInstall
        {
            Build = install.Build,
            Engine = install.Engine,
            Archive = install.Archive.Length > 0 ? install.Archive : null,
            Proxy = install.Proxy.Length > 0 ? install.Proxy : null,
            InstalledAt = (long)stored.InstalledAt,
            VerificationSince = install.VerificationSince is { } since ? (long)since : null,
            Options = UpscalerOptions.From(options),
            Components = install.Components.Take(32).Select(pair =>
            {
                install.Origins.TryGetValue(pair.Key, out var origin);
                return new UpscalerDiagnosisComponent
                {
                    Id = pair.Key,
                    Sha256 = Grouped(pair.Value),
                    Source = origin?.Source,
                    Version = origin?.Version is { } tag && ComponentTag.IsMatch(tag) ? tag : null,
                    Fallback = origin?.Fallback,
                };
            }).ToArray(),
            Args = install.Args.Count > 0 ? install.Args.Take(16).ToArray() : null,
            AddedArgs = install.AddedArgs.Count > 0 ? install.AddedArgs.Take(16).ToArray() : null,
            Anr = install.Anr ? true : null,
            Installed = IsInstalled(install),
        };
        if (install.Engine != "helixsr")
        {
            var manifest = ManifestCheck.Verify(install.Target);
            report.Manifest = new UpscalerDiagnosisManifest
            {
                Present = manifest.Present,
                Complete = manifest.Present ? manifest.Complete : null,
                Files = manifest.Present ? manifest.Files : null,
                Missing = manifest.Present ? manifest.Missing.Take(UpscalerDiagnosis.MaximumNames).ToArray() : null,
                Changed = manifest.Present ? manifest.Changed.Take(UpscalerDiagnosis.MaximumNames).ToArray() : null,
            };
        }

        var verdict = UpscalerVerdict.Read(install, stored.InstalledAt);
        if (install.Engine == "optiscaler")
        {
            var text = IniDiagnostics.ReadText(install.Target);
            report.Ini = text is null
                ? new UpscalerDiagnosisIni { Missing = true }
                : new UpscalerDiagnosisIni { Values = IniDiagnostics.Values(text).Select(pair => new UpscalerIniEdit { Key = pair.Key, Value = pair.Value }).ToArray() };
            report.IniDrift = UpscalerDiagnosisIniDrift.From(IniDiagnostics.Drift(install, text, IniDiagnostics.ModifiedAt(install.Target)));
            report.Advanced = install.Edited.Take(IniDiagnostics.MaximumAdvanced).Select(pair =>
            {
                var request = IniDiagnostics.Request(text, pair.Key, pair.Value);
                return request.Value is null
                    ? new UpscalerDiagnosisEdit { Key = request.Key, ValueOmitted = true }
                    : new UpscalerDiagnosisEdit { Key = request.Key, Value = request.Value };
            }).ToArray();
            var log = OptiScalerLog.Read(install.Target, UpscalerVerdict.Since(Math.Max(stored.InstalledAt, install.VerificationSince ?? 0)));
            var provider = OptiScalerLog.ProviderObservationOf(log);
            var fallback = OptiScalerLog.FallbackOf(install.Engine, install.Build, log);
            report.LogVerdict = OptiScalerLog.Verdict(log);
            report.LogFacts = new UpscalerDiagnosisLog
            {
                Present = log.Present,
                Stale = log.Present ? log.Stale : null,
                Version = log.Version,
                Upscaler = log.Upscaler,
                Input = log.Input,
                FrameGen = log.FrameGeneration,
                FrameGenState = log.FrameGenerationState,
                Fsr4Model = log.Fsr4Model,
                Provider = provider?.Name is { Length: > 0 } name
                    ? string.Join(" ", new[] { name, provider.Version, provider.Model }.Where(part => !string.IsNullOrEmpty(part)))
                    : null,
                Fallback = fallback?.Observed,
                TextureFailure = log.TextureFailure ? true : null,
                Errors = log.Present ? log.Errors : null,
            };
            report.LogExcerpt = LogExcerpt(install.Target);
        }
        else if (install.Engine == "helixsr")
        {
            var facts = HelixLog.ReadInstall(install, Math.Max(stored.InstalledAt, install.VerificationSince ?? 0));
            report.LogVerdict = HelixLog.Verdict(facts);
            report.LogFacts = new UpscalerDiagnosisLog { Present = facts.Present, Stale = facts.Present ? facts.Stale : null, Upscaler = facts.Upscaler };
        }
        else
        {
            report.LogVerdict = "unverifiable";
        }
    }

    /// <summary>The lines of OptiScaler's log that say what it did, most recent last, each cut short.</summary>
    private static string[] LogExcerpt(string target)
    {
        var path = Path.Combine(target, OptiScalerLog.LogName);
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return Array.Empty<string>();
            }

            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var size = (int)Math.Min(stream.Length, OptiScalerLog.MaximumBytes);
            stream.Seek(-size, SeekOrigin.End);
            var bytes = new byte[size];
            var read = 0;
            while (read < size)
            {
                var count = stream.Read(bytes, read, size - read);
                if (count == 0)
                {
                    break;
                }

                read += count;
            }

            return new UTF8Encoding(false, false).GetString(bytes, 0, read)
                .Split('\n')
                .Select(line => line.TrimEnd('\r'))
                .Where(line => Noteworthy.IsMatch(line) && !SkippedLine.IsMatch(line))
                .Select(line => UserHome.Replace(line, "~"))
                .Select(line => line.Length > UpscalerDiagnosis.ExcerptLine ? line.Substring(0, UpscalerDiagnosis.ExcerptLine) : line)
                .TakeLast(LogExcerptLines)
                .ToArray();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return Array.Empty<string>();
        }
    }

    private UpscalerDiagnosisSolution? CurrentSolution(SteamApp app, GameAnalysis analysis, UpscalerBuild build)
    {
        var resolved = Resolved(app, "optiscaler");
        var (automatic, blocked) = Automatic(Recipe(app));
        var inputs = analysis.Inputs.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        var effective = UpscalerPlanner.ForGame(data.Catalog, build, inputs, Gpu.Generation, resolved?.Dependencies ?? Array.Empty<string>());
        var generation = data.Catalog.Asset(effective.Archive)?.Generation ?? 9;
        var plan = SolutionPlan.Resolve(
            data.Catalog,
            Gpu.Generation,
            new PlanAnalysis { Apis = analysis.Apis, Inputs = inputs, Streamline = analysis.Streamline },
            resolved is null
                ? null
                : new PlanRecipe
                {
                    Args = resolved.Args,
                    EffectiveApi = resolved.EffectiveApi,
                    QualityOwner = resolved.QualityOwner,
                    RecommendedInput = resolved.RecommendedInput,
                    Dependencies = resolved.Dependencies,
                },
            generation,
            effective.Engine,
            null,
            automatic is not null);
        return new UpscalerDiagnosisSolution
        {
            EffectiveApi = plan.EffectiveApi,
            ApiSource = plan.ApiSource,
            QualityOwner = plan.QualityOwner,
            RecipeRevision = plan.RecipeRevision,
            RecommendedInput = plan.RecommendedInput,
            InputReconciled = plan.InputReconciled,
            WarningReason = plan.WarningReason,
            Dependencies = plan.Dependencies.Count > 0 ? plan.Dependencies.Take(16).ToArray() : null,
            FrameGenRoute = plan.FrameGenPlan?.Route,
            FrameGenRoutes = plan.OfferedFrameGenPlan is { } offered ? offered.Routes.Select(pair => pair.Key).ToArray() : null,
            BlockedReason = blocked ? "recipe_unresolved" : null,
        };
    }

    /// <summary>The recipe's automatic plan; a recipe Windows cannot satisfy is blocked, not an error.</summary>
    private (AutomaticRecipe? Plan, bool Blocked) Automatic(GameRecipe? recipe)
    {
        try
        {
            return (AutomaticRecipe.Plan(data.Recipes, recipe), false);
        }
        catch (UpscalerException exception) when (exception.Code == "recipe_unsupported")
        {
            return (null, true);
        }
    }

    /// <summary>What sits around the executable that loads code into the game, with whose it is.</summary>
    private UpscalerDiagnosisGameFiles GameFilesReport(SteamApp app, GameAnalysis analysis, string? installTarget)
    {
        var target = analysis.Target ?? installTarget;
        var root = app.Root;
        var owned = new List<string>();
        foreach (var folder in new[] { target, root }.Where(path => !string.IsNullOrEmpty(path)).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (GameFiles.ReadManifest(folder!) is { } manifest)
            {
                var prefix = RelativeUnder(root, folder!);
                owned.AddRange(manifest.Files.Select(pair => prefix + pair.Key));
            }
        }

        var mine = new HashSet<string>(owned.Select(name => name.ToLowerInvariant()), StringComparer.Ordinal);
        string Owner(string relative)
        {
            var path = relative.ToLowerInvariant();
            return mine.Contains(path) || mine.Any(name => name.StartsWith(path.TrimEnd('/') + "/", StringComparison.Ordinal)) ? "panel" : "other";
        }

        var loaders = new List<UpscalerDiagnosisLoader>();
        var storeFiles = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var folder in new[] { target, root }.Where(path => !string.IsNullOrEmpty(path)).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            Dictionary<string, (string Name, bool Directory)> names;
            try
            {
                names = new DirectoryInfo(folder!).EnumerateFileSystemInfos()
                    .Take(4096)
                    .GroupBy(entry => entry.Name, StringComparer.OrdinalIgnoreCase)
                    .ToDictionary(group => group.Key, group => (group.First().Name, (group.First().Attributes & FileAttributes.Directory) != 0), StringComparer.OrdinalIgnoreCase);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            var prefix = RelativeUnder(root, folder!);
            foreach (var name in LoaderFiles.Concat(LoaderFolders))
            {
                if (names.TryGetValue(name, out var entry))
                {
                    var relative = prefix + entry.Name;
                    loaders.Add(new UpscalerDiagnosisLoader { Path = Cut(relative, 160), Directory = entry.Directory, Owner = Owner(relative) });
                }
            }

            foreach (var name in StoreFiles)
            {
                if (names.ContainsKey(name))
                {
                    storeFiles.Add(name);
                }
            }
        }

        return new UpscalerDiagnosisGameFiles
        {
            Loaders = loaders.Take(24).ToArray(),
            StoreFiles = storeFiles.ToArray(),
            AntiCheat = analysis.AntiCheat,
            Apis = analysis.Apis.Take(6).ToArray(),
        };
    }

    private static string RelativeUnder(string root, string folder)
    {
        var separators = new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar };
        var full = Path.GetFullPath(folder).TrimEnd(separators);
        var start = Path.GetFullPath(root).TrimEnd(separators);
        return full.Length > start.Length && full.StartsWith(start, StringComparison.OrdinalIgnoreCase)
            ? full.Substring(start.Length + 1).Replace(Path.DirectorySeparatorChar, '/') + "/"
            : "";
    }

    private static string Cut(string value, int limit) => value.Length > limit ? value.Substring(0, limit) : value;

    private static string Grouped(string digest) =>
        digest.Length == 64 ? string.Join("-", Enumerable.Range(0, 16).Select(index => digest.Substring(index * 4, 4))) : digest;

    private UpscalersResponse Compat(IReadOnlyList<string> appIds)
    {
        var watch = System.Diagnostics.Stopwatch.StartNew();
        var complete = true;
        var rows = new List<UpscalerCompatEntry>();
        foreach (var appId in appIds.Distinct(StringComparer.Ordinal))
        {
            var app = steam.Find(appId);
            if (app is null)
            {
                continue;
            }

            if (watch.Elapsed > OverviewScanBudget)
            {
                complete = false;
                break;
            }

            var recipe = Recipe(app);
            var analysis = Scan(app, recipe);
            rows.Add(new UpscalerCompatEntry
            {
                AppId = appId,
                Inputs = analysis.Inputs.Select(input => input.Key).ToArray(),
                Preferred = UpscalerPlanner.PreferredBuild(data.Catalog, Gpu.Generation, Automatic(recipe).Plan?.Recipe.RecommendedBuild),
            });
        }

        return Ok(compat: new UpscalerCompat { Complete = complete, Games = rows.ToArray() });
    }

    /// <summary>
    /// What Panel just left in OptiScaler.ini, so a report can tell a later rewrite (the game, OptiScaler's own menu, the
    /// user) from a setting Panel never saved. Cleared when the file cannot be read.
    /// </summary>
    private void WroteIni(InstalledUpscaler install, string root)
    {
        if (install.Engine != "optiscaler")
        {
            return;
        }

        string? text;
        try
        {
            text = ReadIni(install.Target, root, strict: false);
        }
        catch (Exception exception) when (exception is UpscalerException or ImageSettingsException)
        {
            text = null;
        }

        install.IniWritten = IniDiagnostics.Written(text, install.Edited, clock());
    }
}
