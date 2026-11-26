using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

public static class UpscalerPaths
{
    // A packaged process sees %LOCALAPPDATA% redirected to the package's LocalCache, but tar.exe is not
    // virtualized: both must use the physical folder or tar unpacks where the companion never looks.
    public static string Root { get; } = Path.Combine(LocalData(), "PanelDeControl", "upscalers");

    private static string LocalData()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var family = PackagedPipeClient.CurrentFamilyName();
        return string.IsNullOrEmpty(family) ? local : Path.Combine(local, "Packages", family, "LocalCache", "Local");
    }

    public static string StateFile => Path.Combine(Root, "state.json");

    public static string CacheRoot => Path.Combine(Root, "cache");

    public static string Tar => Path.Combine(Environment.SystemDirectory, "tar.exe");
}

/// <summary>The catalogs the build ships with: builds, GPU rules and game recipes.</summary>
public sealed class UpscalerData
{
    private const string Prefix = "PanelDeControl.Hardware.Upscalers.";

    public UpscalerData(BuildCatalog catalog, GpuFamily gpuRules, RecipeCatalog? recipes, WikiRecipes? wiki = null)
    {
        Resolver = new RecipeResolver(recipes, wiki);
        Catalog = catalog;
        GpuRules = gpuRules;
        Recipes = recipes;
    }

    public BuildCatalog Catalog { get; }

    public GpuFamily GpuRules { get; }

    public RecipeCatalog? Recipes { get; }

    /// <summary>The game's recipe as Linux resolves it: catalog entry, OptiScaler wiki facts and the RE Engine rule.</summary>
    public RecipeResolver Resolver { get; }

    public static UpscalerData LoadEmbedded()
    {
        var assembly = typeof(UpscalerData).Assembly;
        var catalog = BuildCatalog.Parse(Resource(assembly, "catalog.json") ?? throw new InvalidDataException("catalog_missing"));
        var rules = Resource(assembly, "gpus.json") is { } gpus ? GpuFamily.Parse(gpus) : GpuFamily.None;
        var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        const string recipes = Prefix + "recipes/";
        foreach (var name in assembly.GetManifestResourceNames().Where(name => name.StartsWith(recipes, StringComparison.Ordinal)))
        {
            if (Resource(assembly, name.Substring(Prefix.Length)) is { } bytes)
            {
                files[name.Substring(recipes.Length)] = bytes;
            }
        }

        return new UpscalerData(catalog, rules, files.Count > 0 ? RecipeCatalog.Load(files, skipped => Trace.TraceWarning("Game recipe skipped: " + skipped)) : null, WikiRecipes.Load(Resource(assembly, "recipes_wiki.json")));
    }

    private static byte[]? Resource(Assembly assembly, string name)
    {
        using var stream = assembly.GetManifestResourceStream(Prefix + name);
        if (stream is null)
        {
            return null;
        }

        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return memory.ToArray();
    }
}

/// <summary>Image paths of the running processes, for telling whether a game is open.</summary>
public static class RunningImages
{
    public const int MaximumProcesses = 4000;
    public static readonly TimeSpan Budget = TimeSpan.FromMilliseconds(1500);

    private const uint QueryLimitedInformation = 0x1000;

    /// <summary>Throws <c>process_scan_failed</c> when the list cannot be read in time: a closed game cannot be assumed.</summary>
    [SupportedOSPlatform("windows")]
    public static IReadOnlyList<string> Read()
    {
        var clock = Stopwatch.StartNew();
        var paths = new List<string>();
        Process[] processes;
        try
        {
            processes = Process.GetProcesses();
        }
        catch (Exception exception) when (exception is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            throw new UpscalerException("process_scan_failed");
        }

        try
        {
            if (processes.Length > MaximumProcesses)
            {
                throw new UpscalerException("process_scan_failed");
            }

            foreach (var process in processes)
            {
                if (clock.Elapsed > Budget)
                {
                    throw new UpscalerException("process_scan_failed");
                }

                if (ImagePath(process.Id) is { } path)
                {
                    paths.Add(path);
                }
            }
        }
        finally
        {
            foreach (var process in processes)
            {
                process.Dispose();
            }
        }

        return paths;
    }

    [SupportedOSPlatform("windows")]
    internal static string? ImagePath(int processId)
    {
        var handle = OpenProcess(QueryLimitedInformation, false, processId);
        if (handle == IntPtr.Zero)
        {
            return null;
        }

        try
        {
            var builder = new StringBuilder(1024);
            var size = builder.Capacity;
            return QueryFullProcessImageName(handle, 0, builder, ref size) ? builder.ToString(0, size) : null;
        }
        finally
        {
            CloseHandle(handle);
        }
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint desiredAccess, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(IntPtr process, uint flags, StringBuilder exeName, ref int size);
}

/// <summary>The Steam root the registry names, as the one place libraries start from.</summary>
[SupportedOSPlatform("windows")]
public sealed class SteamRootSource
{
    private readonly PanelDeControl.Hardware.Themes.SteamInstallation installation;

    public SteamRootSource(PanelDeControl.Hardware.Themes.SteamInstallation installation)
    {
        this.installation = installation;
    }

    public IReadOnlyList<string> Roots() => installation.SteamPath is { } path ? new[] { path } : Array.Empty<string>();
}

/// <summary>The Steam games installed on this PC, from each library's appmanifests.</summary>
public sealed class SteamGames
{
    public const int MaximumGames = 1000;

    /// <summary>Steamworks Common Redistributables: installed by Steam itself, listed with the games but never one.</summary>
    public const string SteamworksRedistributablesAppId = "228980";

    private readonly IReadOnlyFileSystem fileSystem;
    private readonly Func<IReadOnlyList<string>> roots;
    private readonly Dictionary<string, string> types = new(StringComparer.Ordinal);
    private readonly object typesLock = new();

    public SteamGames(IReadOnlyFileSystem fileSystem, Func<IReadOnlyList<string>> roots)
    {
        this.fileSystem = fileSystem;
        this.roots = roots;
    }

    public IReadOnlyList<string> Libraries() => SteamLibrary.LibraryPaths(fileSystem, roots());

    public IReadOnlyList<string> Roots() => roots();

    public SteamApp? Find(string appId) => SteamLibrary.FindInstalled(fileSystem, Libraries(), appId);

    /// <summary>Installed games only, as on Linux: whatever Steam files as a tool (runtimes, redistributables) is left out.</summary>
    public IReadOnlyList<SteamApp> All()
    {
        var apps = AllInstalled().Where(app => app.AppId != SteamworksRedistributablesAppId).ToList();
        var tools = Types(apps.Select(app => app.AppId));
        return apps.Where(app => !(tools.TryGetValue(app.AppId, out var type) && type == SteamAppInfo.Tool)).ToList();
    }

    private IReadOnlyDictionary<string, string> Types(IEnumerable<string> appIds)
    {
        var wanted = new HashSet<string>(appIds, StringComparer.Ordinal);
        lock (typesLock)
        {
            wanted.ExceptWith(types.Keys);
            if (wanted.Count > 0)
            {
                foreach (var entry in SteamAppInfo.Types(fileSystem, roots(), wanted))
                {
                    types[entry.Key] = entry.Value;
                }
            }

            return new Dictionary<string, string>(types, StringComparer.Ordinal);
        }
    }

    private IReadOnlyList<SteamApp> AllInstalled()
    {
        var libraries = Libraries();
        var apps = new List<SteamApp>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var library in libraries)
        {
            foreach (var entry in fileSystem.List(Path.Combine(library, "steamapps")))
            {
                var name = entry.Name;
                if (entry.IsDirectory || !name.StartsWith("appmanifest_", StringComparison.OrdinalIgnoreCase)
                    || !name.EndsWith(".acf", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var appId = name.Substring("appmanifest_".Length, name.Length - "appmanifest_".Length - ".acf".Length);
                if (appId.Length is 0 or > 20 || !seen.Add(appId))
                {
                    continue;
                }

                if (SteamLibrary.FindInstalled(fileSystem, new[] { library }, appId) is { } app)
                {
                    apps.Add(app);
                    if (apps.Count >= MaximumGames)
                    {
                        return apps;
                    }
                }
            }
        }

        return apps;
    }
}
