namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// The DLL mode: swaps the game's own FidelityFX libraries for newer ones without OptiScaler, with the steps and checks
/// of the Linux backend's <c>_install_dll</c>. The files go in through <see cref="GameFiles"/> at the game's root, so
/// they come out exactly as they were.
/// </summary>
public sealed class DllInstaller
{
    public const string Provider = "amd_fidelityfx_upscaler_dx12.dll";
    public const string Loader = "amd_fidelityfx_loader_dx12.dll";
    public const string FrameGen = "amd_fidelityfx_framegeneration_dx12.dll";
    public const string Legacy = "amd_fidelityfx_dx12.dll";

    private static readonly HashSet<string> Replaceable = new(StringComparer.Ordinal) { Provider, Loader, FrameGen };
    private static readonly HashSet<string> LegacyReplaceable = new(StringComparer.Ordinal) { Loader, FrameGen };

    private readonly BuildCatalog _catalog;
    private readonly AssetCache _cache;

    public DllInstaller(BuildCatalog catalog, AssetCache cache)
    {
        _catalog = catalog;
        _cache = cache;
    }

    /// <summary>The analysis targets a recipe allows: some games break when their FSR 3.1 library is swapped.</summary>
    public static IReadOnlyList<string> Targets(GameAnalysis analysis, bool legacySwap) =>
        legacySwap ? analysis.DllTargets : analysis.DllTargets.Where(path => Name(path) != Legacy).ToList();

    /// <param name="root">The game's install folder; the manifest goes here.</param>
    /// <param name="analyze">Reads the game folder; called again once the previous install is out.</param>
    /// <param name="legacySwap">False when the game's recipe keeps its own <c>amd_fidelityfx_dx12.dll</c>.</param>
    /// <param name="previous">Panel's current install in this game, taken out once every download is ready.</param>
    /// <param name="claimed">Whether some other install of Panel's owns a folder; leftovers nobody claims are cleared first.</param>
    public async Task<InstalledUpscaler> InstallAsync(string buildId, string root, Func<GameAnalysis> analyze, bool legacySwap,
        InstalledUpscaler? previous, bool confirmAntiCheat, IProgress<long>? progress, CancellationToken cancel,
        Func<string, bool>? claimed = null)
    {
        var build = _catalog.Build(buildId);
        if (build is null || !build.Available)
        {
            throw new UpscalerException("unknown_build");
        }
        if (build.Engine != "dll" || !build.Replace.ContainsKey(Provider) || build.Replace.Keys.Any(key => !Replaceable.Contains(key))
            || build.LegacyReplace.Keys.Any(key => !LegacyReplaceable.Contains(key)))
        {
            throw new UpscalerException("dll_unsupported");
        }

        var analysis = analyze();
        if (analysis.AntiCheat && !confirmAntiCheat)
        {
            throw new UpscalerException("anti_cheat");
        }
        var targets = Targets(analysis, legacySwap);
        var replacements = build.Replace.ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        if (targets.Any(path => Name(path) == Legacy) || previous is not null)
        {
            foreach (var pair in build.LegacyReplace)
            {
                replacements[pair.Key] = pair.Value;
            }
        }
        var assets = new Dictionary<string, UpscalerAsset>(StringComparer.Ordinal);
        foreach (var pair in replacements)
        {
            var asset = _catalog.Asset(pair.Value);
            if (asset is null || asset.Archive || Name(asset.Member ?? asset.FileName) != pair.Key)
            {
                throw new UpscalerException("dll_unsupported");
            }
            assets[pair.Key] = asset;
        }
        CheckTargets(build, targets, assets);
        foreach (var relative in targets)
        {
            var path = Join(root, relative);
            var folder = Path.GetDirectoryName(path)!;
            var checkedPaths = new List<string> { path, Sibling(folder, Provider) };
            if (Name(relative) == Legacy)
            {
                checkedPaths.Add(Sibling(folder, FrameGen));
            }
            if (checkedPaths.Any(candidate => Unsafe(candidate, root)))
            {
                throw new UpscalerException("unsafe_folder");
            }
        }
        if (analysis.Foreign && previous is null)
        {
            throw new UpscalerException("foreign");
        }

        var downloaded = new Dictionary<string, string>(StringComparer.Ordinal);
        var offset = 0L;
        foreach (var pair in assets)
        {
            var start = offset;
            var step = progress is null ? null : new Progress<long>(done => progress.Report(start + done));
            downloaded[pair.Key] = await _cache.EnsureAsync(pair.Value, step, cancel).ConfigureAwait(false);
            offset += pair.Value.Size;
        }

        if (previous is not null)
        {
            OptiScalerInstaller.Uninstall(previous);
        }
        GameFiles.RecoverOrphan(root, previous is null && claimed is not null ? claimed : _ => false);
        if (previous is not null)
        {
            analysis = analyze();
            targets = Targets(analysis, legacySwap);
        }
        if (Directory.Exists(Path.Combine(root, GameManifest.Folder)))
        {
            throw new UpscalerException("dll_conflict");
        }
        CheckTargets(build, targets, assets);
        targets = targets.Where(path => Name(path) != Loader || build.Replace.ContainsKey(Loader)).ToList();

        var sources = new List<KeyValuePair<string, string>>();
        foreach (var relative in targets)
        {
            var path = Join(root, relative);
            if (!File.Exists(path) || Unsafe(path, root))
            {
                throw new UpscalerException("dll_no_target");
            }
            var lower = Name(relative);
            if (lower == Legacy)
            {
                if (!downloaded.ContainsKey(Loader) || !downloaded.ContainsKey(FrameGen))
                {
                    throw new UpscalerException("dll_unsupported");
                }
                Put(sources, relative, downloaded[Loader]);
            }
            else if (downloaded.TryGetValue(lower, out var source))
            {
                Put(sources, relative, source);
            }
            else
            {
                throw new UpscalerException("dll_unsupported");
            }
            var folder = Path.GetDirectoryName(path)!;
            Put(sources, Relative(root, Sibling(folder, Provider)), downloaded[Provider]);
            if (lower == Legacy && !File.Exists(Sibling(folder, FrameGen)))
            {
                Put(sources, Relative(root, Path.Combine(folder, FrameGen)), downloaded[FrameGen]);
            }
        }
        if (sources.Any(pair => Unsafe(Join(root, pair.Key), root)))
        {
            throw new UpscalerException("unsafe_folder");
        }

        var manifest = GameFiles.Apply(root, sources, null);
        return new InstalledUpscaler
        {
            Build = build.Id,
            Engine = "dll",
            Proxy = "",
            Target = root,
            Exe = analysis.Exe,
            DllTargets = targets,
            Components = assets.Values.Select(asset => new KeyValuePair<string, string>(asset.Id, asset.Sha256)).ToList(),
            Files = manifest.Files.Count,
        };
    }

    private static void CheckTargets(UpscalerBuild build, IReadOnlyList<string> targets, IReadOnlyDictionary<string, UpscalerAsset> assets)
    {
        if (targets.Count == 0)
        {
            throw new UpscalerException("dll_no_target");
        }
        if (targets.Any(path => Name(path) == Legacy) && !(assets.ContainsKey(Loader) && assets.ContainsKey(FrameGen)))
        {
            throw new UpscalerException("dll_unsupported");
        }
        var providerFolders = new HashSet<string>(
            targets.Where(path => Name(path) is Provider or Legacy).Select(Folder), StringComparer.OrdinalIgnoreCase);
        if (!build.Replace.ContainsKey(Loader) && targets.Any(path => Name(path) == Loader && !providerFolders.Contains(Folder(path))))
        {
            throw new UpscalerException("dll_unsupported");
        }
    }

    /// <summary>The file of that name already in the folder, whatever its case, or where it would go.</summary>
    private static string Sibling(string folder, string name)
    {
        try
        {
            foreach (var entry in Directory.EnumerateFileSystemEntries(folder))
            {
                if (string.Equals(Path.GetFileName(entry), name, StringComparison.OrdinalIgnoreCase))
                {
                    return entry;
                }
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
        }
        return Path.Combine(folder, name);
    }

    private static bool Unsafe(string path, string root)
    {
        if (IsLink(path))
        {
            return true;
        }
        var full = Path.GetFullPath(path);
        var top = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!full.StartsWith(top, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }
        // A junction or symlink between the game folder and the file would carry it somewhere else.
        for (var folder = Path.GetDirectoryName(full); folder is not null && folder.Length >= top.Length; folder = Path.GetDirectoryName(folder))
        {
            if (IsLink(folder))
            {
                return true;
            }
        }
        return false;
    }

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

    private static string Join(string root, string relative) => Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar));

    private static string Relative(string root, string path) =>
        Path.GetFullPath(path).Substring(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar).Length + 1).Replace(Path.DirectorySeparatorChar, '/');

    private static string Folder(string relative)
    {
        var index = relative.Replace('\\', '/').LastIndexOf('/');
        return index < 0 ? "" : relative.Substring(0, index);
    }

    private static string Name(string path) => Path.GetFileName(path.Replace('\\', '/')).ToLowerInvariant();

    private static void Put(List<KeyValuePair<string, string>> sources, string relative, string path)
    {
        var index = sources.FindIndex(pair => GameManifest.PathComparer.Equals(pair.Key, relative));
        if (index >= 0)
        {
            sources[index] = new KeyValuePair<string, string>(relative, path);
        }
        else
        {
            sources.Add(new KeyValuePair<string, string>(relative, path));
        }
    }
}
