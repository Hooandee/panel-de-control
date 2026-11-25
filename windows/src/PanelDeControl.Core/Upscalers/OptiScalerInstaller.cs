using System.Text;
using static PanelDeControl.Core.Upscalers.InstallPaths;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What Panel left in a game, kept by the caller so it can replace or remove it later.</summary>
/// <summary>Whether a tracked component is its newest verified release or the catalog's pinned one, and why.</summary>
public sealed class ComponentOrigin
{
    public ComponentOrigin(string source, string? version, string? fallback)
    {
        Source = source;
        Version = version;
        Fallback = fallback;
    }

    public string Source { get; }

    public string? Version { get; }

    public string? Fallback { get; }
}

public sealed class InstalledUpscaler
{
    public string Build { get; set; } = "";

    public string Archive { get; set; } = "";

    public string Engine { get; set; } = "optiscaler";

    public string Proxy { get; set; } = "";

    public string Target { get; set; } = "";

    public string? Exe { get; set; }

    public UpscalerChoice Options { get; set; } = new();

    public string? FrameGenRoute { get; set; }

    /// <summary>The game libraries the DLL mode swapped, relative to <see cref="Target"/>.</summary>
    public IReadOnlyList<string> DllTargets { get; set; } = Array.Empty<string>();

    /// <summary>Whether the Apex Neural Rendering FG add-on went in beside OptiScaler.</summary>
    public bool Anr { get; set; }

    /// <summary>Launch arguments the game's recipe asks for on Windows.</summary>
    public IReadOnlyList<string> Args { get; set; } = Array.Empty<string>();

    /// <summary>The arguments Panel itself added to Steam's launch options, and only those come out on removal.</summary>
    public IReadOnlyList<string> AddedArgs { get; set; } = Array.Empty<string>();

    /// <summary>OptiScaler.ini keys Panel owns, sorted as Linux stores them.</summary>
    public IReadOnlyList<string> Managed { get; set; } = Array.Empty<string>();

    /// <summary>Each asset that went in and its hash.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> Components { get; set; } = Array.Empty<KeyValuePair<string, string>>();

    /// <summary>Where a tracked component came from, by asset id: <c>latest</c> with its release tag, or <c>pinned</c> with the reason.</summary>
    public IReadOnlyDictionary<string, ComponentOrigin> Origins { get; set; } = new Dictionary<string, ComponentOrigin>();

    /// <summary>Settings Panel changed in the game's own config under the user's profile, so removal can put them back.</summary>
    public IReadOnlyList<GameConfigRecord> GameConfig { get; set; } = Array.Empty<GameConfigRecord>();

    public int Files { get; set; }

    /// <summary>The user's mod that went in with this install, as <c>filename</c> and <c>id</c>.</summary>
    public KeyValuePair<string, string>? Mod { get; set; }

    /// <summary>HelixSR's route inside its bridge; only the FSR drop-in exists.</summary>
    public string Way { get; set; } = "";

    /// <summary>Where HelixSR's bridge put its DLLs and record, which can differ from <see cref="Target"/>.</summary>
    public string ExeFolder { get; set; } = "";

    /// <summary>HelixSR's own log.</summary>
    public string Log { get; set; } = "";

    /// <summary>HelixSR's install record, the file whose presence says HelixSR is still in the game.</summary>
    public string HelixFile { get; set; } = "";

    /// <summary>OptiScaler.ini keys the user changed in the advanced editor; they survive a repair or a new version.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> Edited { get; set; } = Array.Empty<KeyValuePair<string, string>>();

    /// <summary>Sharpness keys the image controls own, so a new quality or a reinstall keeps them.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> ImageOverrides { get; set; } = Array.Empty<KeyValuePair<string, string>>();

    /// <summary>What Panel left in OptiScaler.ini the last time it wrote it; a report compares it with the file as it is now.</summary>
    public IniWritten? IniWritten { get; set; }

    /// <summary>When a new model went in without a reinstall: the log only counts from then on (Unix seconds).</summary>
    public double? VerificationSince { get; set; }

    /// <summary>Set by an install that kept the image controls' sharpness, for the caller to store; never saved with the install.</summary>
    public ImageSettingsReceipt? ImageReceipt { get; set; }
}

/// <summary>The user's mod for a game as an install needs it; <see cref="Sources"/> are the stored copies by destination beside the exe.</summary>
public sealed class UserModInstall
{
    public string Filename { get; set; } = "";

    public string Id { get; set; } = "";

    /// <summary>The exe's folder relative to the game folder when the mod was added, '/' separated.</summary>
    public string Target { get; set; } = "";

    public string GameRoot { get; set; } = "";

    public IReadOnlyList<KeyValuePair<string, string>> Sources { get; set; } = Array.Empty<KeyValuePair<string, string>>();
}

public sealed class OptiScalerInstallRequest
{
    public string Build { get; set; } = "";

    public string? Proxy { get; set; }

    public UpscalerChoice Choice { get; set; } = new();

    public bool ConfirmAntiCheat { get; set; }
}

/// <summary>
/// Installs an OptiScaler build into one game with the steps of the Linux backend's <c>install</c>: every asset is
/// downloaded and verified before the game is touched, the previous install comes out first, and the files go in
/// through <see cref="GameFiles"/> so they can be restored exactly. Checks that depend on Windows itself (game running,
/// Steam updating, protected folder) belong to the caller.
/// </summary>
public sealed class OptiScalerInstaller
{
    private const string DefaultProxy = "dxgi.dll";
    private readonly BuildCatalog _catalog;
    private readonly AssetCache _cache;
    private readonly string _gpu;
    private readonly string? _profile;
    private readonly string? _documents;
    private readonly LatestReleases? _latest;

    /// <param name="profile">The user's profile folder, where a recipe's game settings live; the real one when omitted.</param>
    /// <param name="documents">The Documents folder for settings under <c>Documents/</c>; the real one (OneDrive included) when no profile is given, else <c>profile/Documents</c>.</param>
    /// <param name="latest">Resolves each tracked asset to its newest verified release; the catalog's pinned asset when it is null or cannot.</param>
    public OptiScalerInstaller(BuildCatalog catalog, AssetCache cache, string gpu, string? profile = null, string? documents = null, LatestReleases? latest = null)
    {
        _latest = latest;
        _catalog = catalog;
        _cache = cache;
        _gpu = gpu;
        _profile = profile ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        _documents = documents ?? (profile is null ? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) : null);
    }

    /// <param name="analyze">Reads the game folder; called again once the previous install is out.</param>
    /// <param name="claimed">Whether some other install of Panel's owns a folder.</param>
    /// <param name="automatic">The recipe's dependency packages and configuration, from <see cref="AutomaticRecipe.Plan"/>.</param>
    public async Task<InstalledUpscaler> InstallAsync(Func<GameAnalysis> analyze, ResolvedRecipe? recipe, OptiScalerInstallRequest request,
        InstalledUpscaler? previous, Func<string, bool> claimed, IProgress<long>? progress, CancellationToken cancel,
        AutomaticRecipe? automatic = null, UserModInstall? mod = null, Func<RecipeDependency, IReadOnlyDictionary<string, string>>? userFiles = null)
    {
        var build = _catalog.Build(request.Build);
        if (build is null || !build.Available)
        {
            throw new UpscalerException("unknown_build");
        }
        if (build.Engine != "optiscaler")
        {
            throw new UpscalerException("engine_unsupported", build.Engine);
        }
        if (request.Proxy is not null && !_catalog.Proxies.Contains(request.Proxy))
        {
            throw new UpscalerException("invalid_proxy");
        }
        var analysis = analyze();
        if (analysis.Target is null)
        {
            throw new UpscalerException("no_exe");
        }
        if (analysis.AntiCheat && !request.ConfirmAntiCheat)
        {
            throw new UpscalerException("anti_cheat");
        }
        var wantsAnr = request.Choice.FrameGen && request.Choice.FrameGenRoute == "anr";
        if (wantsAnr && !UpscalerPlanner.AnrCapable(_catalog, build, _gpu))
        {
            throw new UpscalerException("anr_build");
        }
        var target = analysis.Target;
        var effective = UpscalerPlanner.ForGame(_catalog, build, Inputs(analysis), _gpu, recipe?.Dependencies ?? Array.Empty<string>());
        RequestedFrameGen(analysis, recipe, effective, request.Choice, automatic is not null);

        // Everything is downloaded before the current install comes out: a failed or cancelled download leaves the
        // game exactly as it was.
        GameFiles.RecoverOrphan(target, claimed);
        var pinnedOnly = new HashSet<string>(StringComparer.Ordinal);
        var chosen = new Dictionary<string, UpscalerAsset>(StringComparer.Ordinal);
        var first = Needed(effective, wantsAnr, recipe, automatic);
        var paths = await FetchAsync(first, pinnedOnly, chosen, progress, cancel).ConfigureAwait(false);
        var releaseAsset = _catalog.Asset(effective.Archive)!;
        try
        {
            OptiScalerSources(paths[releaseAsset.Id], releaseAsset.Generation);
        }
        catch (UpscalerException) when (Newer(chosen, releaseAsset.Id))
        {
            // A newer OptiScaler laid out differently: the catalog's own release, before the game is touched.
            Reject(chosen, releaseAsset.Id);
            pinnedOnly.Add(releaseAsset.Id);
            paths = await FetchAsync(first, pinnedOnly, chosen, progress, cancel).ConfigureAwait(false);
            OptiScalerSources(paths[releaseAsset.Id], releaseAsset.Generation);
        }
        if (wantsAnr)
        {
            try
            {
                AnrSources(paths[_catalog.AnrFrameGen], "");
            }
            catch (UpscalerException) when (Newer(chosen, _catalog.AnrFrameGen))
            {
                // A newer add-on laid out differently: the catalog's own release, before the game is touched.
                Reject(chosen, _catalog.AnrFrameGen);
                pinnedOnly.Add(_catalog.AnrFrameGen);
                paths = await FetchAsync(first, pinnedOnly, chosen, progress, cancel).ConfigureAwait(false);
                AnrSources(paths[_catalog.AnrFrameGen], "");
            }
        }
        try
        {
            automatic?.Sources(paths, userFiles);
        }
        catch (UpscalerException) when (automatic is not null && automatic.Assets().Any(asset => Newer(chosen, asset.Id)))
        {
            foreach (var asset in automatic.Assets())
            {
                Reject(chosen, asset.Id);
                pinnedOnly.Add(asset.Id);
            }
            paths = await FetchAsync(first, pinnedOnly, chosen, progress, cancel).ConfigureAwait(false);
            automatic.Sources(paths, userFiles);
        }
        if (mod is { Sources.Count: > 0 } && !string.Equals(mod.Target, RelativeTo(mod.GameRoot, target), StringComparison.OrdinalIgnoreCase))
        {
            throw new UpscalerException("mod_moved");
        }
        cancel.ThrowIfCancellationRequested();
        // The mod's settings as the user left them: the old install takes those files away with it.
        var keptSettings = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var relative in mod is { Sources.Count: > 0 } && recipe is not null ? recipe.ModSettings.Keys : Enumerable.Empty<string>())
        {
            keptSettings[relative] = SmallText(Path.Combine(target, relative.Replace('/', Path.DirectorySeparatorChar)));
        }
        var optiScalerBefore = previous is not null && previous.Engine == "optiscaler";
        var edited = optiScalerBefore ? previous!.Edited : Array.Empty<KeyValuePair<string, string>>();
        var imageKept = optiScalerBefore && previous!.ImageOverrides.Count > 0 && ReadIni(previous.Target) is { } oldIni
            ? UpscalerSettings.ImageOverrides(previous, oldIni)
            : Array.Empty<KeyValuePair<string, string>>();
        if (previous is not null)
        {
            Uninstall(previous);
            // Files the game replaced since (an update) stayed behind with stale backups: those copies go, the game's stay.
            GameFiles.RecoverOrphan(target, _ => false);
            analysis = analyze();
            target = analysis.Target ?? throw new UpscalerException("no_exe");
        }
        if (analysis.Foreign)
        {
            throw new UpscalerException("foreign");
        }

        var proxy = request.Proxy ?? (recipe?.Proxy is { } named && _catalog.Proxies.Contains(named) ? named : null) ?? DefaultProxy;
        var modSources = mod?.Sources ?? Array.Empty<KeyValuePair<string, string>>();
        if (modSources.Any(pair => string.Equals(pair.Key, proxy, StringComparison.OrdinalIgnoreCase)))
        {
            // The mod brings its own loader under OptiScaler's usual name: OptiScaler takes another.
            proxy = _catalog.Proxies.FirstOrDefault(name => name != "d3d12.dll" && !modSources.Any(pair => string.Equals(pair.Key, name, StringComparison.OrdinalIgnoreCase)))
                ?? throw new UpscalerException("mod_conflict");
        }
        effective = UpscalerPlanner.ForGame(_catalog, build, Inputs(analysis), _gpu, recipe?.Dependencies ?? Array.Empty<string>());
        var assets = Needed(effective, wantsAnr, recipe, automatic);
        if (assets.Any(asset => !paths.ContainsKey(asset.Id)))
        {
            // The previous install is already out of the game: this fetch finishes the swap.
            paths = await FetchAsync(assets, pinnedOnly, chosen, progress, CancellationToken.None).ConfigureAwait(false);
        }
        var archive = _catalog.Asset(effective.Archive)!;
        var sources = OptiScalerSources(paths[archive.Id], archive.Generation);
        var iniPath = sources[GameFiles.IniName];
        var injector = sources["OptiScaler.dll"];
        var baseIni = File.ReadAllText(iniPath, new UTF8Encoding(false, false));
        sources.Remove(GameFiles.IniName);
        sources.Remove("OptiScaler.dll");
        if (!string.IsNullOrEmpty(effective.Injector))
        {
            injector = paths[effective.Injector!];
        }
        var ordered = automatic is null ? new List<KeyValuePair<string, string>>() : automatic.Sources(paths, userFiles).ToList();
        foreach (var pair in sources)
        {
            Put(ordered, pair.Key, pair.Value);
        }
        Put(ordered, proxy, injector);
        var prefix = string.IsNullOrEmpty(effective.ExtraDir) ? "" : effective.ExtraDir + "/";
        foreach (var pair in effective.Replace)
        {
            Put(ordered, prefix + pair.Key, paths[pair.Value]);
        }
        foreach (var id in effective.Assets)
        {
            Put(ordered, prefix + _catalog.Asset(id)!.FileName, paths[id]);
        }
        if (recipe is not null)
        {
            foreach (var pair in recipe.Files)
            {
                Put(ordered, pair.Key, paths[pair.Value]);
            }
            if (recipe.OptiPatcher && OptiPatcher() is { } optiPatcher)
            {
                Put(ordered, prefix + "plugins/OptiPatcher.asi", paths[optiPatcher.Id]);
            }
            foreach (var name in recipe.OptiScalerRootFiles)
            {
                var source = ordered.FirstOrDefault(pair => pair.Key == prefix + name);
                if (prefix.Length > 0 && source.Key is not null && !ordered.Any(pair => pair.Key == name))
                {
                    Put(ordered, name, source.Value);
                }
            }
        }

        if (wantsAnr)
        {
            foreach (var pair in AnrSources(paths[_catalog.AnrFrameGen], prefix))
            {
                Put(ordered, pair.Key, pair.Value);
            }
        }

        var owned = new List<string>();
        if (modSources.Count > 0)
        {
            if (modSources.Any(pair => string.Equals(pair.Key, GameFiles.IniName, StringComparison.OrdinalIgnoreCase)
                || ordered.Any(known => GameManifest.PathComparer.Equals(known.Key, pair.Key))))
            {
                throw new UpscalerException("mod_conflict");
            }
            ordered.InsertRange(0, modSources);
            owned.AddRange(modSources.Select(pair => pair.Key));
        }

        var frameGen = RequestedFrameGen(analysis, recipe, effective, request.Choice, automatic is not null);
        var panel = PanelIni.Compute(_catalog, effective, recipe?.Ini, recipe?.OptiPatcher == true, request.Choice, frameGen, previous?.Anr == true);
        // Hand edits from the advanced editor survive a repair or a new version; Panel's own keys win over them.
        var carried = UpscalerSettings.CarriedEdits(edited, panel.Select(pair => pair.Key));
        var beforeImage = IniText.Apply(IniText.Apply(baseIni, panel), carried);
        var image = imageKept.Where(pair => IniText.Read(baseIni, pair.Key) is not null).ToList();
        var ini = IniText.Apply(beforeImage, image);
        var receipt = image.Count == 0 ? null : new ImageSettingsReceipt
        {
            Target = Path.Combine(target, GameFiles.IniName),
            Original = image.Select(pair => new KeyValuePair<string, string>(pair.Key, IniText.Read(beforeImage, pair.Key)!)).ToList(),
            Applied = image.ToList(),
        };
        var seeds = Path.Combine(_cache.Root, ".recipe-" + Guid.NewGuid().ToString("N"));
        GameManifest manifest;
        try
        {
            if (automatic is not null && automatic.Configuration.Count > 0)
            {
                Directory.CreateDirectory(seeds);
                foreach (var pair in automatic.ConfiguredSources(target, seeds))
                {
                    Put(ordered, pair.Key, pair.Value);
                }
            }
            if (recipe is not null && (recipe.Files.Values.Contains(ReframeworkConfig.Asset) || automatic?.PlacedFiles.Any(name => string.Equals(name, "dinput8.dll", StringComparison.OrdinalIgnoreCase)) == true))
            {
                Put(ordered, ReframeworkConfig.FileName, SeedReframework(target, seeds, recipe, request.Choice));
            }
            foreach (var settings in modSources.Count > 0 && recipe is not null ? recipe.ModSettings : new Dictionary<string, IReadOnlyDictionary<string, string>>())
            {
                var text = keptSettings.TryGetValue(settings.Key, out var kept) && kept.Length > 0
                    ? kept
                    : SmallText(Path.Combine(target, settings.Key.Replace('/', Path.DirectorySeparatorChar)));
                var seed = Path.Combine(seeds, "mod-settings", settings.Key.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(seed)!);
                File.WriteAllText(seed, IniText.Apply(text, settings.Value), new UTF8Encoding(false));
                Put(ordered, settings.Key, seed);
                owned.Add(settings.Key);
            }
            manifest = GameFiles.Apply(target, ordered, ini, protect: recipe?.ProtectDlls == true,
                configuration: automatic?.Configuration, owned: owned);
        }
        finally
        {
            try
            {
                if (Directory.Exists(seeds))
                {
                    Directory.Delete(seeds, true);
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
            }
        }
        return new InstalledUpscaler
        {
            Build = effective.Id,
            Archive = effective.Archive,
            Proxy = proxy,
            Target = target,
            Exe = analysis.Exe,
            Options = Clean(request.Choice),
            FrameGenRoute = frameGen?.Route,
            Anr = wantsAnr,
            Args = recipe?.Args ?? Array.Empty<string>(),
            Managed = panel.Select(pair => pair.Key).OrderBy(key => key, StringComparer.Ordinal).ToList(),
            Components = assets.Select(asset => new KeyValuePair<string, string>(asset.Id, chosen.TryGetValue(asset.Id, out var picked) ? picked.Sha256 : asset.Sha256)).ToList(),
            Origins = Origins(assets, chosen, pinnedOnly),
            GameConfig = recipe is { GameConfig.Count: > 0 } ? GameConfigFiles.Carry(previous?.GameConfig, GameConfigFiles.Apply(_profile, recipe.GameConfig, _documents)).ToList() : Array.Empty<GameConfigRecord>(),
            Files = manifest.Files.Count,
            Mod = mod is { Sources.Count: > 0 } ? new KeyValuePair<string, string>(mod.Filename, mod.Id) : null,
            Edited = carried,
            ImageOverrides = image,
            ImageReceipt = receipt,
        };
    }

    /// <summary>Takes an install out; returns the files kept because the game replaced them since.</summary>
    public static IReadOnlyList<string> Uninstall(InstalledUpscaler install)
    {
        var kept = GameFiles.Remove(install.Target);
        // Settings go back only once the files are out: a refused removal leaves both as they were.
        if (GameFiles.ReadManifest(install.Target) is null)
        {
            GameConfigFiles.Restore(install.GameConfig);
        }
        return kept;
    }

    /// <summary>REFramework's config with its menu closed (and its upscaler on Panel's quality), written beside the game's own.</summary>
    private static string SeedReframework(string target, string seeds, ResolvedRecipe recipe, UpscalerChoice choice)
    {
        var existing = Path.Combine(target, ReframeworkConfig.FileName);
        var current = "";
        try
        {
            var info = new FileInfo(existing);
            if (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0 && info.Length < ReframeworkConfig.MaximumBytes)
            {
                current = File.ReadAllText(existing, new UTF8Encoding(false, false));
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
        var values = ReframeworkConfig.Closed.Select(pair => new KeyValuePair<string, string?>(pair.Key, pair.Value)).ToList();
        if (recipe.ReframeworkUpscaler)
        {
            values.AddRange(ReframeworkConfig.Upscaler(choice.Quality));
        }
        Directory.CreateDirectory(seeds);
        var seed = Path.Combine(seeds, ReframeworkConfig.FileName);
        File.WriteAllText(seed, ReframeworkConfig.WithKeys(current, values), new UTF8Encoding(false));
        return seed;
    }

    private static string SmallText(string path)
    {
        try
        {
            var info = new FileInfo(path);
            return info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0 && info.Length < ReframeworkConfig.MaximumBytes
                ? File.ReadAllText(path, new UTF8Encoding(false, false))
                : "";
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return "";
        }
    }

    private static string RelativeTo(string root, string folder)
    {
        var separators = new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar };
        var full = Path.GetFullPath(folder).TrimEnd(separators);
        var start = Path.GetFullPath(root).TrimEnd(separators);
        return full.Length > start.Length && full.StartsWith(start, StringComparison.OrdinalIgnoreCase)
            ? full.Substring(start.Length + 1).Replace(Path.DirectorySeparatorChar, '/')
            : "";
    }

    private static string? ReadIni(string target)
    {
        try
        {
            var info = new FileInfo(Path.Combine(target, GameFiles.IniName));
            return info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0 && info.Length <= ImageSettings.MaximumBytes
                ? File.ReadAllText(info.FullName, new UTF8Encoding(false, false))
                : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private UpscalerAsset? OptiPatcher() =>
        _catalog.Archives.TryGetValue("optipatcher", out var id) ? _catalog.Asset(id) : null;

    /// <summary>The frame generation route this game can take for the choice; <c>fg_route_unavailable</c> when it asks for one it cannot.</summary>
    public FrameGenPlan? RequestedFrameGen(GameAnalysis analysis, ResolvedRecipe? recipe, UpscalerBuild effective, UpscalerChoice choice,
        bool dependenciesReady)
    {
        var generation = _catalog.Asset(effective.Archive)!.Generation;
        var plan = SolutionPlan.Resolve(_catalog, _gpu, new PlanAnalysis { Apis = analysis.Apis, Inputs = Inputs(analysis), Streamline = analysis.Streamline },
            recipe is null ? null : new PlanRecipe
            {
                Args = recipe.Args,
                EffectiveApi = recipe.EffectiveApi,
                QualityOwner = recipe.QualityOwner,
                RecommendedInput = recipe.RecommendedInput,
                Dependencies = recipe.Dependencies,
            },
            generation, effective.Engine, choice.FrameGenRoute, dependenciesReady);
        var requested = SolutionPlan.RequestedFrameGen(plan, choice.FrameGen, choice.FrameGenRoute);
        if (choice.FrameGen && requested is null)
        {
            throw new UpscalerException("fg_route_unavailable");
        }
        return requested;
    }

    private IReadOnlyList<UpscalerAsset> Needed(UpscalerBuild build, bool anr, ResolvedRecipe? recipe, AutomaticRecipe? automatic)
    {
        var assets = UpscalerPlanner.BuildAssets(_catalog, build).ToList();
        foreach (var id in recipe?.Files.Values.Distinct(StringComparer.Ordinal) ?? Enumerable.Empty<string>())
        {
            var asset = _catalog.Asset(id) ?? throw new UpscalerException("recipe_unsupported", "unknown recipe asset " + id);
            if (!assets.Contains(asset))
            {
                assets.Add(asset);
            }
        }
        if (recipe?.OptiPatcher == true && OptiPatcher() is { } optiPatcher && !assets.Contains(optiPatcher))
        {
            assets.Add(optiPatcher);
        }
        if (anr && _catalog.Asset(_catalog.AnrFrameGen) is { } addOn && !assets.Contains(addOn))
        {
            assets.Add(addOn);
        }
        foreach (var asset in automatic?.Assets() ?? Array.Empty<UpscalerAsset>())
        {
            if (assets.All(known => known.Id != asset.Id))
            {
                assets.Add(asset);
            }
        }
        return assets;
    }

    /// <summary>ANR's provider folder as OptiScaler 10 finds it: <c>custom/&lt;provider&gt;/</c> next to OptiScaler.dll.</summary>
    private IReadOnlyList<KeyValuePair<string, string>> AnrSources(string unpacked, string prefix)
    {
        var root = Path.Combine(unpacked, _catalog.AnrProvider);
        if (!File.Exists(Path.Combine(root, "dlssg", "nvngx_dlssg.dll")))
        {
            throw new UpscalerException("anr_layout");
        }
        return Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .OrderBy(path => path, StringComparer.Ordinal)
            .Select(path => new KeyValuePair<string, string>(
                prefix + "custom/" + _catalog.AnrProvider + "/" + path.Substring(root.Length + 1).Replace(Path.DirectorySeparatorChar, '/'), path))
            .ToList();
    }

    private async Task<Dictionary<string, string>> FetchAsync(IReadOnlyList<UpscalerAsset> assets, ISet<string> pinnedOnly, IDictionary<string, UpscalerAsset> chosen,
        IProgress<long>? progress, CancellationToken cancel)
    {
        var paths = new Dictionary<string, string>(StringComparer.Ordinal);
        var offset = 0L;
        foreach (var asset in assets)
        {
            var start = offset;
            var step = progress is null ? null : new Progress<long>(done => progress.Report(start + done));
            var (path, picked) = await LatestAssets.EnsureAsync(_cache, _latest, asset, pinnedOnly.Contains(asset.Id), step, cancel).ConfigureAwait(false);
            paths[asset.Id] = path;
            chosen[asset.Id] = picked;
            offset += picked.Size;
        }
        return paths;
    }

    private Dictionary<string, ComponentOrigin> Origins(IEnumerable<UpscalerAsset> assets, IDictionary<string, UpscalerAsset> chosen, ISet<string> pinnedOnly)
    {
        var origins = new Dictionary<string, ComponentOrigin>(StringComparer.Ordinal);
        foreach (var asset in assets)
        {
            if (_latest is null || !_latest.Tracked(asset))
            {
                continue;
            }

            var version = chosen.TryGetValue(asset.Id, out var picked) && picked.Sha256 != asset.Sha256 ? _latest.Version(picked) : null;
            origins[asset.Id] = version is not null
                ? new ComponentOrigin("latest", version, null)
                : new ComponentOrigin("pinned", null, pinnedOnly.Contains(asset.Id) ? "layout" : "unresolved");
        }

        return origins;
    }

    private static Dictionary<string, string> OptiScalerSources(string unpacked, int generation)
    {
        var sources = OptiScalerRelease.Sources(unpacked, generation);
        if (!sources.ContainsKey(GameFiles.IniName) || !sources.ContainsKey("OptiScaler.dll"))
        {
            throw new UpscalerException("unpack_failed", "release without OptiScaler.dll or OptiScaler.ini");
        }
        return sources;
    }

    private void Reject(IDictionary<string, UpscalerAsset> chosen, string id)
    {
        if (Newer(chosen, id))
        {
            _latest?.Reject(chosen[id].Sha256);
        }
    }

    private bool Newer(IDictionary<string, UpscalerAsset> chosen, string id) =>
        chosen.TryGetValue(id, out var picked) && _catalog.Asset(id) is { } pinned && picked.Sha256 != pinned.Sha256;

    private UpscalerChoice Clean(UpscalerChoice choice) => new()
    {
        Quality = choice.Quality is not null && _catalog.QualityRatios.ContainsKey(choice.Quality) ? choice.Quality : null,
        Sharpness = choice.Sharpness is not null && _catalog.Sharpness.ContainsKey(choice.Sharpness) ? choice.Sharpness : null,
        FrameGen = choice.FrameGen,
        FrameGenRoute = choice.FrameGenRoute is "game" or "optiscaler" or "anr" ? choice.FrameGenRoute : null,
        Model = string.IsNullOrEmpty(choice.Model) ? null : choice.Model,
    };

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> Inputs(GameAnalysis analysis) =>
        analysis.Inputs.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
}
