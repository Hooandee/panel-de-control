using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Upscalers;

/// <summary>Which executable in a game folder creates the device, and which upscalers the game ships.</summary>
public static class GameFolder
{
    /// <summary>Unreal keeps plugin libraries seven or eight folders down (Plugins/Nvidia/DLSS/Binaries/ThirdParty/Win64).</summary>
    public const int MaxDepth = 9;
    public const int MaxPeScans = 12;
    public const int MaxCandidates = 6;
    public const int MaxInputsPerKind = 4;
    public const string PanelManifestFolder = ".pdc-upscaler";

    /// <summary>Library names that reveal an upscaler or frame generator, by input kind, in reporting order.</summary>
    public static readonly IReadOnlyList<KeyValuePair<string, string[]>> Inputs = new[]
    {
        Input("fsr31", "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_dx12.dll", "amd_fidelityfx_loader_dx12.dll"),
        Input("fsr2", "ffx_fsr2_api_x64.dll", "ffx_fsr2_api_dx12_x64.dll", "ffx_fsr2_api_vk_x64.dll"),
        Input("dlss", "nvngx_dlss.dll"),
        Input("xess", "libxess.dll"),
        Input("streamline", "sl.interposer.dll"),
        Input("dlssg", "nvngx_dlssg.dll", "sl.dlss_g.dll"),
        // FSR 3.1.0-3.1.3 ship upscaler and frame generation in one amd_fidelityfx_dx12.dll.
        Input("fsrfg", "amd_fidelityfx_framegeneration_dx12.dll", "amd_fidelityfx_dx12.dll"),
        Input("xefg", "libxess_fg.dll"),
    };

    public static readonly IReadOnlyList<string> AntiCheatMarkers = new[] { "easyanticheat", "battleye", "eac_launcher", "beservice" };

    public static readonly IReadOnlyList<string> ForeignMarkers = new[]
    {
        "OptiScaler.ini", "OptiScaler.log", "FRAMEGEN_PATCH", "helixsr-install.json", "HelixSR-Scaler.files",
    };

    /// <summary>Upscalers compiled into the game's own executable leave their entry points as strings.</summary>
    public static readonly IReadOnlyList<KeyValuePair<string, string>> EmbeddedEntryPoints = new[]
    {
        new KeyValuePair<string, string>("fsr2", "ffxFsr2ContextCreate"),
        new KeyValuePair<string, string>("fsr31", "ffxFsr3UpscalerContextCreate"),
        new KeyValuePair<string, string>("xess", "xessD3D12CreateContext"),
    };

    private static readonly IReadOnlyList<KeyValuePair<string, string>> ShippedNames = new[]
    {
        new KeyValuePair<string, string>("dlss", "DLSS"),
        new KeyValuePair<string, string>("fsr31", "FSR 3.1"),
        new KeyValuePair<string, string>("fsr2", "FSR 2"),
        new KeyValuePair<string, string>("xess", "XeSS"),
    };

    private static readonly HashSet<string> CombinedLibraries = new(StringComparer.Ordinal)
    {
        "amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_loader_dx12.dll", "amd_fidelityfx_dx12.dll",
    };

    private static readonly HashSet<string> SkippedFolders = new(StringComparer.Ordinal)
    {
        "__installer", "_commonredist", "redist", "redistributables", "directx", "support", "extras", "optiscaler",
    };

    private static readonly Regex SkippedExecutable = new(
        "crash|unins|redist|setup|prereq|dotnet|helper|easyanticheat|battleye|eac_|" +
        "d3dconfig|compiler|7za|reporter|webhelper|cefprocess|vc_?redist|dxsetup|launcherpatcher",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex StreamlineVersion = new(@"(?:^|v)(\d+)[.,]\d+", RegexOptions.CultureInvariant);

    private const long ScoreSizeStep = 8L * 1024 * 1024;
    private const int ScanChunk = 1024 * 1024;

    public static GameAnalysis Analyze(IReadOnlyFileSystem fileSystem, string root, string? chosenExe = null, string? recipeExe = null)
    {
        var executables = new List<(int Score, string Relative, long Size)>();
        var inputs = Inputs.ToDictionary(item => item.Key, _ => new List<string>(), StringComparer.Ordinal);
        var dllTargets = new List<string>();
        var antiCheat = false;
        foreach (var folder in Walk(fileSystem, root))
        {
            var ours = InstalledByPanel(fileSystem, folder.Path);
            var lowerFolder = folder.Path.Replace('\\', '/').ToLowerInvariant();
            if (AntiCheatMarkers.Any(marker => lowerFolder.Contains(marker)))
            {
                antiCheat = true;
            }

            foreach (var file in folder.Files)
            {
                var lower = file.ToLowerInvariant();
                var relative = Combine(folder.Relative, file);
                var path = FileSystemPath.Join(root, relative);
                if (CombinedLibraries.Contains(lower) && !ours.Contains(lower) && fileSystem.IsFile(path) && !fileSystem.IsSymbolicLink(path))
                {
                    dllTargets.Add(relative);
                }

                if (AntiCheatMarkers.Any(marker => lower.Contains(marker)))
                {
                    antiCheat = true;
                }

                foreach (var input in Inputs)
                {
                    if (input.Value.Contains(lower) && !ours.Contains(lower))
                    {
                        inputs[input.Key].Add(relative);
                    }
                }

                if (lower.EndsWith(".exe", StringComparison.Ordinal) && !SkippedExecutable.IsMatch(lower))
                {
                    var size = fileSystem.Length(path);
                    if (size is null)
                    {
                        continue;
                    }

                    executables.Add((Score(relative, size.Value), relative, size.Value));
                }
            }
        }

        var candidates = executables
            .OrderByDescending(item => item.Score)
            .ThenByDescending(item => item.Size)
            .ThenBy(item => item.Relative, StringComparer.Ordinal)
            .Take(MaxPeScans)
            .Select(item =>
            {
                var apis = GraphicsApis(fileSystem, FileSystemPath.Join(root, item.Relative));
                var score = item.Score + (apis.Any(api => api is "d3d12" or "d3d11" or "vulkan") ? 30 : 0);
                return new ExeCandidate(item.Relative, apis, item.Size, score);
            })
            .OrderByDescending(candidate => candidate.Score)
            .ThenBy(candidate => candidate.Exe, StringComparer.Ordinal)
            .ToList();

        var manual = false;
        var selected = candidates.FirstOrDefault();
        if (string.IsNullOrEmpty(chosenExe) && !string.IsNullOrEmpty(recipeExe) && fileSystem.IsFile(FileSystemPath.Join(root, recipeExe!)))
        {
            selected = Known(fileSystem, root, candidates, recipeExe!);
        }

        if (!string.IsNullOrEmpty(chosenExe) && fileSystem.IsFile(FileSystemPath.Join(root, chosenExe!)))
        {
            manual = true;
            selected = Known(fileSystem, root, candidates, chosenExe!);
        }

        string? target = null;
        if (selected is not null)
        {
            var parent = FileSystemPath.RelativeParent(selected.Exe);
            target = parent.Length == 0 ? root : FileSystemPath.Join(root, parent);
            foreach (var kind in EmbeddedUpscalers(fileSystem, FileSystemPath.Join(root, selected.Exe)))
            {
                if (inputs[kind].Count == 0)
                {
                    inputs[kind].Add(selected.Exe);
                }
            }
        }

        var foreign = target is not null
            && !fileSystem.Exists(FileSystemPath.Join(target, PanelManifestFolder))
            && ForeignMarkers.Any(marker => fileSystem.Exists(FileSystemPath.Join(target, marker)));
        var streamline = inputs["streamline"].OrderBy(path => path, StringComparer.Ordinal).FirstOrDefault();
        return new GameAnalysis(
            candidates.Take(MaxCandidates).ToArray(),
            selected?.Exe,
            selected?.Apis ?? Array.Empty<string>(),
            manual,
            target,
            Inputs
                .Where(input => inputs[input.Key].Count > 0)
                .Select(input => new KeyValuePair<string, IReadOnlyList<string>>(
                    input.Key,
                    inputs[input.Key].OrderBy(path => path, StringComparer.Ordinal).Take(MaxInputsPerKind).ToArray()))
                .ToArray(),
            dllTargets.OrderBy(path => path, StringComparer.Ordinal).ToArray(),
            streamline is null ? null : StreamlineMajor(fileSystem, FileSystemPath.Join(root, streamline)),
            antiCheat,
            foreign,
            foreign && target is not null ? ForeignUpscalerIdentity.Read(fileSystem, target) : null);
    }

    /// <summary>The DLSS, FSR and XeSS libraries the game folder carries, by name, in a fixed order.</summary>
    public static IReadOnlyList<string> ShippedUpscalers(IReadOnlyFileSystem fileSystem, string root)
    {
        var found = new HashSet<string>(StringComparer.Ordinal);
        (long Size, string Path)? largest = null;
        foreach (var folder in Walk(fileSystem, root))
        {
            var ours = InstalledByPanel(fileSystem, folder.Path);
            foreach (var file in folder.Files)
            {
                var lower = file.ToLowerInvariant();
                foreach (var shipped in ShippedNames)
                {
                    if (InputNames(shipped.Key).Contains(lower) && !ours.Contains(lower))
                    {
                        found.Add(shipped.Key);
                    }
                }

                if (lower.EndsWith(".exe", StringComparison.Ordinal) && !SkippedExecutable.IsMatch(lower))
                {
                    var path = FileSystemPath.Join(folder.Path, file);
                    var size = fileSystem.Length(path);
                    if (size is not null && (largest is null || size.Value > largest.Value.Size))
                    {
                        largest = (size.Value, path);
                    }
                }
            }
        }

        if (largest is not null && found.Count == 0)
        {
            found.UnionWith(EmbeddedUpscalers(fileSystem, largest.Value.Path));
        }

        return ShippedNames.Where(item => found.Contains(item.Key)).Select(item => item.Value).ToArray();
    }

    /// <summary>
    /// The exe's graphics imports. RE Engine games import only d3d11/dxgi and load D3D12 at runtime; the Agility
    /// SDK beside their exe is what gives the D3D12 device away. Other games keep what they import.
    /// </summary>
    public static IReadOnlyList<string> GraphicsApis(IReadOnlyFileSystem fileSystem, string exe)
    {
        var apis = new HashSet<string>(PeImage.GraphicsApis(fileSystem, exe), StringComparer.Ordinal);
        var folder = ParentOf(exe);
        // Windows matches file names without case, so the pak glob does too.
        if (fileSystem.IsFile(FileSystemPath.Join(folder, "D3D12/D3D12Core.dll"))
            && fileSystem.List(folder).Any(entry => entry.Name.StartsWith("re_chunk_000.pak", StringComparison.OrdinalIgnoreCase)))
        {
            apis.Remove("d3d11");
            apis.Add("d3d12");
        }

        return apis.OrderBy(api => api, StringComparer.Ordinal).ToArray();
    }

    public static ISet<string> EmbeddedUpscalers(IReadOnlyFileSystem fileSystem, string exe)
    {
        var found = new HashSet<string>(StringComparer.Ordinal);
        var needles = EmbeddedEntryPoints.Select(item => (item.Key, Bytes: Encoding.ASCII.GetBytes(item.Value))).ToArray();
        var overlap = needles.Max(item => item.Bytes.Length) - 1;
        try
        {
            using var stream = fileSystem.OpenRead(exe);
            if (stream is null)
            {
                return found;
            }

            var buffer = new byte[ScanChunk + overlap];
            var carried = 0;
            int read;
            while ((read = stream.Read(buffer, carried, ScanChunk)) > 0)
            {
                var window = new byte[carried + read];
                Array.Copy(buffer, window, window.Length);
                foreach (var (kind, needle) in needles)
                {
                    if (!found.Contains(kind) && ByteSearch.IndexOf(window, needle, 0) >= 0)
                    {
                        found.Add(kind);
                    }
                }

                carried = Math.Min(overlap, window.Length);
                Array.Copy(window, window.Length - carried, buffer, 0, carried);
            }
        }
        catch (IOException)
        {
            found.Clear();
        }
        catch (UnauthorizedAccessException)
        {
            found.Clear();
        }

        return found;
    }

    /// <summary>NVIDIA leaves FileVersion out of some builds; OriginalFilename then carries "v2.14.1".</summary>
    public static int? StreamlineMajor(IReadOnlyFileSystem fileSystem, string path)
    {
        var strings = PeImage.VersionStrings(fileSystem, path);
        foreach (var key in new[] { "FileVersion", "ProductVersion", "OriginalFilename" })
        {
            var match = StreamlineVersion.Match(strings.TryGetValue(key, out var value) ? value : string.Empty);
            if (match.Success)
            {
                return PythonText.ParseDigits(match.Groups[1].Value);
            }
        }

        return null;
    }

    private static ExeCandidate Known(IReadOnlyFileSystem fileSystem, string root, IReadOnlyList<ExeCandidate> candidates, string exe)
    {
        var path = FileSystemPath.Join(root, exe);
        return candidates.FirstOrDefault(candidate => candidate.Exe == exe)
            ?? new ExeCandidate(exe, GraphicsApis(fileSystem, path), fileSystem.Length(path) ?? 0, 0);
    }

    private static int Score(string relative, long size)
    {
        var lowerRelative = relative.ToLowerInvariant();
        var slash = lowerRelative.LastIndexOf('/');
        var name = slash < 0 ? lowerRelative : lowerRelative.Substring(slash + 1);
        var score = 0;
        if (name.EndsWith("-win64-shipping.exe", StringComparison.Ordinal))
        {
            score += 50;
        }

        if (lowerRelative.Contains("binaries/win64"))
        {
            score += 20;
        }

        if (lowerRelative.StartsWith("engine/", StringComparison.Ordinal))
        {
            score -= 40;
        }

        if (name.Contains("launcher"))
        {
            score -= 25;
        }

        return score + (int)Math.Min(size / ScoreSizeStep, 20);
    }

    /// <summary>Lower-case names Panel de Control put in the folder; replaced game files stay the game's.</summary>
    private static ISet<string> InstalledByPanel(IReadOnlyFileSystem fileSystem, string folder)
    {
        var ours = new HashSet<string>(StringComparer.Ordinal);
        var data = FileSystemPath.ReadAtMost(fileSystem, FileSystemPath.Join(folder, PanelManifestFolder + "/manifest.json"), int.MaxValue);
        string text;
        try
        {
            text = data is null ? string.Empty : new UTF8Encoding(false, true).GetString(data);
        }
        catch (DecoderFallbackException)
        {
            return ours;
        }

        var manifest = data is null ? null : JsonTree.Parse(text);
        if (manifest is null || !JsonTree.IsObject(manifest))
        {
            return ours;
        }

        var backups = new HashSet<string>(StringComparer.Ordinal);
        if (JsonTree.Member(manifest, "backups") is { } backupList && JsonTree.IsArray(backupList))
        {
            backups.UnionWith(backupList.Elements().Where(JsonTree.IsString).Select(item => item.Value));
        }

        var files = JsonTree.Member(manifest, "files");
        IEnumerable<string> names = files is null
            ? Array.Empty<string>()
            : JsonTree.IsObject(files)
                ? files.Elements().Select(JsonTree.Key)
                : JsonTree.IsArray(files) ? files.Elements().Where(JsonTree.IsString).Select(item => item.Value) : Array.Empty<string>();
        foreach (var name in names)
        {
            if (!backups.Contains(name) && !name.Contains('/'))
            {
                ours.Add(name.ToLowerInvariant());
            }
        }

        return ours;
    }

    private static IEnumerable<WalkedFolder> Walk(IReadOnlyFileSystem fileSystem, string root)
    {
        if (!fileSystem.IsDirectory(root))
        {
            yield break;
        }

        var pending = new Stack<(string Path, string Relative, int Depth)>();
        pending.Push((root, string.Empty, 0));
        while (pending.Count > 0)
        {
            var (path, relative, depth) = pending.Pop();
            var entries = fileSystem.List(path).OrderBy(entry => entry.Name, StringComparer.Ordinal).ToArray();
            yield return new WalkedFolder(path, relative, entries.Where(entry => !entry.IsDirectory).Select(entry => entry.Name).ToArray());
            if (depth >= MaxDepth)
            {
                continue;
            }

            foreach (var entry in entries.Reverse())
            {
                if (entry.IsDirectory && !entry.IsSymbolicLink && !SkippedFolders.Contains(entry.Name.ToLowerInvariant())
                    && !entry.Name.StartsWith(".", StringComparison.Ordinal))
                {
                    pending.Push((FileSystemPath.Join(path, entry.Name), Combine(relative, entry.Name), depth + 1));
                }
            }
        }
    }

    private static string[] InputNames(string kind) => Inputs.First(item => item.Key == kind).Value;

    private static string Combine(string relative, string name) => relative.Length == 0 ? name : relative + "/" + name;

    private static string ParentOf(string path)
    {
        var slash = Math.Max(path.LastIndexOf('/'), path.LastIndexOf('\\'));
        return slash <= 0 ? (slash == 0 ? path.Substring(0, 1) : ".") : path.Substring(0, slash);
    }

    private static KeyValuePair<string, string[]> Input(string kind, params string[] names) => new(kind, names);

    private sealed class WalkedFolder
    {
        public WalkedFolder(string path, string relative, IReadOnlyList<string> files)
        {
            Path = path;
            Relative = relative;
            Files = files;
        }

        public string Path { get; }

        public string Relative { get; }

        public IReadOnlyList<string> Files { get; }
    }
}
