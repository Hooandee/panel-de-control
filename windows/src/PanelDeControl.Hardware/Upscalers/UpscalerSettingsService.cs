using System.Text;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>
/// Changing an install without reinstalling, as the Linux backend's <c>configure</c>, <c>ini_schema</c>/<c>set_ini</c>
/// and image settings do. Every write goes through one lock and replaces OptiScaler.ini only if it still holds what was read.
/// </summary>
public sealed partial class UpscalerService
{
    private const long MaximumIniBytes = 1024 * 1024;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private static readonly UTF8Encoding LenientUtf8 = new(false, false);
    private readonly object settingsLock = new();

    private UpscalersResponse Configure(UpscalersRequest request)
    {
        lock (settingsLock)
        {
            var appId = request.AppId!;
            var stored = store.Install(appId) ?? throw new UpscalerException("not_patched");
            var install = stored.Install;
            if (install.Engine == "dll")
            {
                throw new UpscalerException("dll_no_options");
            }

            EnsureNoJob(appId);
            var catalog = data.Catalog;
            var build = catalog.Build(install.Build);
            if (request.Quality is not null && !catalog.QualityRatios.ContainsKey(request.Quality))
            {
                throw new UpscalerException("invalid_quality");
            }

            if (request.Sharpness is not null && !catalog.Sharpness.ContainsKey(request.Sharpness))
            {
                throw new UpscalerException("invalid_sharpness");
            }

            if (request.Model is not null && (build is null || build.Models.All(model => model.Id != request.Model)))
            {
                throw new UpscalerException("invalid_model");
            }

            var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
            var choice = new UpscalerChoice
            {
                Quality = request.Quality,
                Sharpness = request.Sharpness,
                FrameGen = request.FrameGen == true,
                FrameGenRoute = request.FrameGenRoute,
                Model = request.Model,
            };
            var current = install.Options;
            var running = GameGuards.IsRunningUnder(app.Root, runningImages());
            var optiScaler = install.Engine == "optiscaler";
            if (optiScaler && current.FrameGen && !choice.FrameGen && choice.Quality == current.Quality && choice.Sharpness == current.Sharpness
                && choice.FrameGenRoute == current.FrameGenRoute && choice.Model == current.Model)
            {
                // Only turning frame generation off: nothing is re-planned, so a game that changed since cannot refuse it.
                if (running)
                {
                    throw new UpscalerException("running");
                }

                var text = ReadIni(install.Target, app.Root, strict: false);
                WriteIni(install.Target, app.Root, text, IniText.Apply(text, UpscalerSettings.FrameGenOff(install)));
                install.Options = Copy(current, frameGen: false);
                SaveInstall(appId, install, stored.InstalledAt);
                return Ok(options: UpscalerOptions.From(install.Options));
            }

            ResolvedRecipe? recipe = null;
            FrameGenPlan? frameGen = null;
            if (optiScaler && build is not null)
            {
                recipe = Resolved(app, "optiscaler");
                var automatic = AutomaticRecipe.Plan(data.Recipes, Recipe(app));
                frameGen = new OptiScalerInstaller(catalog, cache, Gpu.Generation)
                    .RequestedFrameGen(Analyze(app, recipe?.Exe), recipe, build, choice, automatic is not null);
            }

            if (choice.FrameGen && choice.FrameGenRoute == "anr" && !install.Anr)
            {
                // Its files only go in with an install on OptiScaler 10.
                throw new UpscalerException("anr_reinstall");
            }

            if (running)
            {
                return ConfigureRunning(appId, stored, choice, app.Root, recipe);
            }

            if (install.Engine == "helixsr")
            {
                install.Options = Copy(choice, frameGen: false);
                SaveInstall(appId, install, stored.InstalledAt);
                return Ok(options: UpscalerOptions.From(install.Options));
            }

            var before = ReadIni(install.Target, app.Root, strict: false);
            WriteIni(install.Target, app.Root, before, IniText.Apply(before, UpscalerSettings.ConfigureOverrides(catalog, install, choice, frameGen, before)));
            if (recipe?.ReframeworkUpscaler == true)
            {
                RewriteReframework(install.Target, choice.Quality);
            }

            var modelChanged = !SameMapping(UpscalerPlanner.ModelOverrides(build, choice.Model), UpscalerPlanner.ModelOverrides(build, current.Model));
            install.Options = Copy(choice, frameGen: choice.FrameGen);
            install.FrameGenRoute = frameGen?.Route;
            var now = clock();
            if (modelChanged)
            {
                install.VerificationSince = now;
            }

            SaveInstall(appId, install, stored.InstalledAt);
            if (modelChanged)
            {
                try
                {
                    store.AddHistory(appId, new UpscalerHistoryItem(now, install.Build, install.Proxy.Length > 0 ? install.Proxy : null, "pending", install.Exe, install.Options.Model));
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    log("upscalers.history", exception.GetType().Name);
                }
            }

            Record(appId, "configure", "done", install.Build, null);
            return Ok(options: UpscalerOptions.From(install.Options));
        }
    }

    /// <summary>
    /// Quality and sharpness while the game runs: OptiScaler reads its INI only at start, so the change waits for the next
    /// launch; anything else waits for the game to close.
    /// </summary>
    private UpscalersResponse ConfigureRunning(string appId, StoredUpscaler stored, UpscalerChoice choice, string root, ResolvedRecipe? recipe)
    {
        var install = stored.Install;
        var current = install.Options;
        // REFramework rewrites its own config on exit, so its upscaler quality can only change with the game closed.
        if (install.Engine == "helixsr" || choice.FrameGen != current.FrameGen || choice.FrameGenRoute != current.FrameGenRoute || choice.Model != current.Model
            || (recipe?.ReframeworkUpscaler == true && choice.Quality != current.Quality))
        {
            throw new UpscalerException("running");
        }

        var text = ReadIni(install.Target, root, strict: false);
        WriteIni(install.Target, root, text, IniText.Apply(text, UpscalerSettings.RunningOverrides(data.Catalog, install, choice, text)));
        install.Options = Copy(choice, frameGen: current.FrameGen);
        SaveInstall(appId, install, stored.InstalledAt);
        Record(appId, "configure", "done", install.Build, null);
        return Ok(options: UpscalerOptions.From(install.Options, live: false));
    }

    private UpscalersResponse IniSchema(string appId)
    {
        var (install, root) = IniInstall(appId);
        var text = ReadIni(install.Target, root, strict: false);
        return Ok(ini: UpscalerIniSection.From(IniText.Schema(text, UpscalerSettings.ManagedKeys(data.Catalog, install))));
    }

    /// <summary>One key the user changed by hand; Panel's own keys stay Panel's so it never overwrites a choice silently.</summary>
    private UpscalersResponse SetIni(string appId, string key, string value)
    {
        lock (settingsLock)
        {
            EnsureNoJob(appId);
            var (install, root) = IniInstall(appId);
            var text = ReadIni(install.Target, root, strict: false);
            var edit = UpscalerSettings.ValidateEdit(text, key, value, UpscalerSettings.ManagedKeys(data.Catalog, install));
            WriteIni(install.Target, root, text, IniText.Apply(text, new[] { edit }));
            var edited = install.Edited.Where(pair => pair.Key != edit.Key).ToList();
            var index = install.Edited.ToList().FindIndex(pair => pair.Key == edit.Key);
            edited.Insert(index < 0 ? edited.Count : index, edit);
            install.Edited = edited;
            SaveInstall(appId, install, store.Install(appId)!.InstalledAt);
            Record(appId, "ini_set", "done", install.Build, null);
            return Ok(iniEdit: new UpscalerIniEdit { Key = edit.Key, Value = edit.Value });
        }
    }

    private UpscalersResponse ImageSettingsOf(string appId)
    {
        lock (settingsLock)
        {
            return Ok(image: UpscalerImageSettings.From(ImageState(appId)));
        }
    }

    private ImageSettingsState ImageState(string appId)
    {
        try
        {
            var target = ImageTarget(appId, false);
            var receipt = store.ImageReceipt(appId);
            return ImageSettings.State(target.Text, target.Helix, receipt is not null && SamePath(receipt.Target, target.Path) && receipt.Applied.Count > 0);
        }
        catch (Exception error) when (error is UpscalerException or ImageSettingsException)
        {
            return new ImageSettingsState { Reason = error is UpscalerException upscaler ? upscaler.Code : ((ImageSettingsException)error).Code };
        }
    }

    private UpscalersResponse SetImage(UpscalersRequest request)
    {
        lock (settingsLock)
        {
            var appId = request.AppId!;
            try
            {
                var target = ImageTarget(appId, true);
                var wanted = new ImageSettingsRequest
                {
                    Sharpness = request.SharpnessEnabled is { } enabled ? new ImageSharpness { Enabled = enabled, Value = request.SharpnessValue } : null,
                    Int8 = request.Int8,
                };
                var changes = ImageSettings.Changes(wanted, ImageSettings.State(target.Text, target.Helix, false), target.Text);
                var previous = store.ImageReceipt(appId);
                var receipt = ImageSettings.Receipt(previous is not null && SamePath(previous.Target, target.Path) ? previous : null, target.Path, target.Text, changes);
                receipt.Target = target.Path;
                var stored = target.Owned ? store.Install(appId) : null;
                if (stored is not null)
                {
                    stored.Install.ImageOverrides = receipt.Applied.ToList();
                }

                // The receipt is saved before the file changes: if the write fails the old one comes back.
                store.SetImageReceipt(appId, receipt, stored);
                try
                {
                    WriteIni(Path.GetDirectoryName(target.Path)!, target.Root, target.Text, IniText.Apply(target.Text, changes), strict: true);
                }
                catch
                {
                    if (ReadIni(Path.GetDirectoryName(target.Path)!, target.Root, strict: false) == target.Text)
                    {
                        store.SetImageReceipt(appId, previous, stored is null ? null : store.Install(appId) is { } now ? WithImage(now, previous) : null);
                    }

                    throw;
                }

                if (stored is not null)
                {
                    WriteRecord(stored.Install, stored.InstalledAt);
                }

                Record(appId, "image_settings", "done", stored?.Install.Build, null);
                return Ok(image: UpscalerImageSettings.From(ImageState(appId)));
            }
            catch (ImageSettingsException error)
            {
                throw new UpscalerException(error.Code);
            }
        }
    }

    private UpscalersResponse RestoreImage(string appId)
    {
        lock (settingsLock)
        {
            try
            {
                var target = ImageTarget(appId, true);
                var receipt = store.ImageReceipt(appId);
                if (receipt is null || !SamePath(receipt.Target, target.Path))
                {
                    throw new UpscalerException("image_settings_changed");
                }

                WriteIni(Path.GetDirectoryName(target.Path)!, target.Root, target.Text, ImageSettings.Restored(target.Text, receipt), strict: true);
                var stored = target.Owned ? store.Install(appId) : null;
                if (stored is not null)
                {
                    stored.Install.ImageOverrides = Array.Empty<KeyValuePair<string, string>>();
                }

                store.SetImageReceipt(appId, null, stored);
                if (stored is not null)
                {
                    WriteRecord(stored.Install, stored.InstalledAt);
                }

                Record(appId, "image_settings_restored", "done", stored?.Install.Build, null);
                return Ok(image: UpscalerImageSettings.From(ImageState(appId)));
            }
            catch (ImageSettingsException error)
            {
                throw new UpscalerException(error.Code);
            }
        }
    }

    private sealed record ImageFile(string Root, string Path, string Text, bool Helix, bool Owned);

    /// <summary>Panel's own OptiScaler install, or another tool's HLX DLSS whose INT8 switch Panel only adjusts (<c>_image_target</c>).</summary>
    private ImageFile ImageTarget(string appId, bool writing)
    {
        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        if (writing)
        {
            EnsureNoJob(null);
            if (app.UpdateState is { } update)
            {
                throw new UpscalerException(update == SteamUpdateState.Running ? "updating" : "update_pending");
            }
        }

        var install = store.Install(appId)?.Install;
        var owned = install is not null && install.Engine == "optiscaler";
        // OptiScaler reads its INI only at start and never writes it while running, so Panel's own install can take a
        // new value for the next launch; another tool's files wait for the game to close.
        if (writing && !owned)
        {
            GameGuards.EnsureClosed(app, runningImages());
        }

        if (install is not null && !owned)
        {
            throw new UpscalerException("not_supported");
        }

        string target;
        if (owned)
        {
            target = install!.Target;
        }
        else
        {
            target = Analyze(app, Recipe(app)?.Exe).Target ?? throw new UpscalerException("unsupported_layout");
        }

        var text = ReadIni(target, app.Root, strict: true);
        var helix = false;
        if (!owned)
        {
            var identity = ForeignUpscalerIdentity.Read(fileSystem, target);
            if (identity.Engine != "helixsr" || identity.Variant != "dlss" || identity.ManifestError)
            {
                throw new UpscalerException("unsupported_layout");
            }

            if (!text.Contains("HelixSR Scaler") || !ImageSettings.Values(text).ContainsKey("HelixSR.Int8"))
            {
                throw new UpscalerException("unsupported_layout");
            }

            var providers = new[] { Path.Combine(target, "HelixSR", "helixsr.dll"), Path.Combine(target, "HelixSR-fsrfg", "amd_fidelityfx_dx12.dll") };
            if (!providers.Any(PlainFile))
            {
                throw new UpscalerException("unsupported_layout");
            }

            helix = true;
        }

        return new ImageFile(app.Root, Path.Combine(target, GameFiles.IniName), text, helix, owned);
    }

    private (InstalledUpscaler Install, string Root) IniInstall(string appId)
    {
        var install = store.Install(appId)?.Install;
        if (install is null || install.Engine is "helixsr" or "dll")
        {
            throw new UpscalerException("not_patched");
        }

        var app = steam.Find(appId) ?? throw new UpscalerException("not_installed");
        return (install, app.Root);
    }

    private void EnsureNoJob(string? appId)
    {
        if (jobs.Snapshot() is { State: UpscalerJobStates.Running } job && (appId is null || job.AppId == appId))
        {
            throw new UpscalerException("busy");
        }
    }

    private void SaveInstall(string appId, InstalledUpscaler install, double installedAt)
    {
        store.SetInstall(appId, install, installedAt);
        WriteRecord(install, installedAt);
    }

    private void RewriteReframework(string target, string? quality)
    {
        var path = Path.Combine(target, ReframeworkConfig.FileName);
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0 || info.Length > ReframeworkConfig.MaximumBytes)
            {
                return;
            }

            var current = File.ReadAllText(path, LenientUtf8);
            File.WriteAllText(path, ReframeworkConfig.WithKeys(current, ReframeworkConfig.Upscaler(quality)), new UTF8Encoding(false));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            log("upscalers.reframework", exception.GetType().Name);
        }
    }

    /// <summary>
    /// OptiScaler.ini under the game folder, refusing links on the way (a junction could point the write anywhere).
    /// <c>broken</c> when it cannot be read; image controls also refuse anything that is not plain UTF-8 under 256 KiB.
    /// </summary>
    private static string ReadIni(string folder, string root, bool strict)
    {
        var path = Path.Combine(folder, GameFiles.IniName);
        if (!InsideWithoutLinks(path, root))
        {
            throw new UpscalerException(strict ? "unsafe_path" : "broken");
        }

        try
        {
            var info = new FileInfo(path);
            if (!info.Exists)
            {
                throw new UpscalerException(strict ? "unsafe_path" : "broken");
            }

            if (info.Length > (strict ? ImageSettings.MaximumBytes : MaximumIniBytes))
            {
                throw strict ? new ImageSettingsException("invalid_config") : new UpscalerException("broken");
            }

            var bytes = File.ReadAllBytes(path);
            return (strict ? StrictUtf8 : LenientUtf8).GetString(bytes);
        }
        catch (DecoderFallbackException)
        {
            throw new ImageSettingsException("invalid_config");
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new UpscalerException(strict ? "unsafe_path" : "broken");
        }
    }

    /// <summary>Replaces OptiScaler.ini through a temporary file beside it, only if it still holds <paramref name="before"/>.</summary>
    private static void WriteIni(string folder, string root, string before, string after, bool strict = false)
    {
        var path = Path.Combine(folder, GameFiles.IniName);
        var changed = strict ? "image_settings_changed" : "ini_changed";
        if (ReadIni(folder, root, strict: false) != before)
        {
            throw new UpscalerException(changed);
        }

        if (after == before)
        {
            return;
        }

        var temporary = Path.Combine(folder, ".pdc-ini-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            File.WriteAllBytes(temporary, LenientUtf8.GetBytes(after));
            if (ReadIni(folder, root, strict: false) != before)
            {
                throw new UpscalerException(changed);
            }

            File.Replace(temporary, path, null);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new UpscalerException("broken", exception.GetType().Name);
        }
        finally
        {
            try
            {
                File.Delete(temporary);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }

        if (ReadIni(folder, root, strict: false) != after)
        {
            throw new UpscalerException(changed);
        }
    }

    private static bool InsideWithoutLinks(string path, string root)
    {
        try
        {
            var full = Path.GetFullPath(path);
            var top = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
            if (!full.StartsWith(top + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            for (var current = full; current.Length > top.Length; current = Path.GetDirectoryName(current)!)
            {
                var info = new FileInfo(current);
                if (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    return false;
                }

                var directory = new DirectoryInfo(current);
                if (directory.Exists && (directory.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    return false;
                }
            }

            return true;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return false;
        }
    }

    private static bool PlainFile(string path)
    {
        try
        {
            var info = new FileInfo(path);
            return info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0
                && (info.Directory?.Attributes & FileAttributes.ReparsePoint) is null or 0;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static StoredUpscaler WithImage(StoredUpscaler stored, ImageSettingsReceipt? receipt)
    {
        stored.Install.ImageOverrides = receipt?.Applied.ToList() ?? new List<KeyValuePair<string, string>>();
        return stored;
    }

    private static UpscalerChoice Copy(UpscalerChoice choice, bool frameGen) => new()
    {
        Quality = choice.Quality,
        Sharpness = choice.Sharpness,
        FrameGen = frameGen,
        FrameGenRoute = choice.FrameGenRoute,
        Model = choice.Model,
    };

    private static bool SameMapping(IReadOnlyDictionary<string, string> left, IReadOnlyDictionary<string, string> right) =>
        left.Count == right.Count && left.All(pair => right.TryGetValue(pair.Key, out var value) && value == pair.Value);
}
