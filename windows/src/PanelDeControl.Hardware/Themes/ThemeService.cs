using System.Net.Http;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

public interface IThemeCatalogSource
{
    Task<byte[]> CatalogAsync(CancellationToken cancellationToken);

    Task<byte[]> ArtifactAsync(ThemeRelease release, CancellationToken cancellationToken);
}

public sealed class OfficialThemeCatalogSource : IThemeCatalogSource, IDisposable
{
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(30) };

    public async Task<byte[]> CatalogAsync(CancellationToken cancellationToken) =>
        await ReadBoundedAsync(ThemeCatalog.CatalogUrl, ThemeCatalog.MaximumMetadataBytes, cancellationToken).ConfigureAwait(false);

    public async Task<byte[]> ArtifactAsync(ThemeRelease release, CancellationToken cancellationToken) =>
        await ReadBoundedAsync(ThemeCatalog.ArtifactUrl(release.CatalogId, release.Version), release.Artifact.Size, cancellationToken).ConfigureAwait(false);

    public void Dispose() => http.Dispose();

    private async Task<byte[]> ReadBoundedAsync(Uri url, long maximum, CancellationToken cancellationToken)
    {
        using var response = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        if (response.RequestMessage?.RequestUri?.Host != url.Host)
        {
            throw new HttpRequestException("Theme channel redirected away from the official host");
        }

        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using var buffer = new MemoryStream();
        var chunk = new byte[81920];
        int read;
        while ((read = await stream.ReadAsync(chunk, cancellationToken).ConfigureAwait(false)) > 0)
        {
            if (buffer.Length + read > maximum)
            {
                throw new InvalidDataException("Theme channel response is larger than allowed");
            }

            buffer.Write(chunk, 0, read);
        }

        return buffer.ToArray();
    }
}

public sealed record ThemeCatalogState(IReadOnlyList<ThemeRelease> Releases, string? ErrorCode, DateTimeOffset? CheckedAt);

/// <summary>
/// Theme operations behind the widget: catalog, install, activation and options. Every change is
/// persisted first and then confirmed by the engine's readback.
/// </summary>
public sealed class ThemeService
{
    private static readonly TimeSpan CatalogFreshness = TimeSpan.FromMinutes(30);
    private static readonly TimeSpan CatalogRetry = TimeSpan.FromMinutes(1);

    private readonly string libraryRoot;
    private readonly ThemeSettingsStore settings;
    private readonly ThemePackageInstaller installer;
    private readonly IThemeCatalogSource channel;
    private readonly ISteamInstallation steam;
    private readonly SemaphoreSlim operations = new(1, 1);
    private ThemeCatalogState catalog = new(Array.Empty<ThemeRelease>(), null, null);
    private int catalogRefreshing;

    public ThemeService(string libraryRoot, IThemeCatalogSource channel, ISteamInstallation steam)
    {
        this.libraryRoot = libraryRoot;
        this.channel = channel;
        this.steam = steam;
        settings = new ThemeSettingsStore(libraryRoot);
        installer = new ThemePackageInstaller(libraryRoot);
        ThemePackageInstaller.RecoverInterruptedInstalls(libraryRoot);
    }

    public ThemeCatalogState Catalog => catalog;

    public ThemeLibrarySnapshot Library() => ThemeLibrary.Scan(libraryRoot);

    public IReadOnlyList<ThemeSetting> Settings() => settings.Read();

    public async Task<ThemeCatalogState> RefreshCatalogAsync(bool force, CancellationToken cancellationToken)
    {
        var freshness = catalog.ErrorCode is null ? CatalogFreshness : CatalogRetry;
        if (!force && catalog.CheckedAt is { } checkedAt && DateTimeOffset.UtcNow - checkedAt < freshness)
        {
            return catalog;
        }

        if (!force && Interlocked.CompareExchange(ref catalogRefreshing, 1, 0) != 0)
        {
            return catalog;
        }

        try
        {
            return await FetchCatalogAsync(cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            if (!force)
            {
                Interlocked.Exchange(ref catalogRefreshing, 0);
            }
        }
    }

    private async Task<ThemeCatalogState> FetchCatalogAsync(CancellationToken cancellationToken)
    {
        try
        {
            var releases = ThemeCatalog.Parse(await channel.CatalogAsync(cancellationToken).ConfigureAwait(false));
            catalog = new ThemeCatalogState(releases, null, DateTimeOffset.UtcNow);
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or FormatException or InvalidDataException)
        {
            cancellationToken.ThrowIfCancellationRequested();
            CompanionLog.Write("themes.catalog", exception);
            catalog = catalog with
            {
                ErrorCode = exception is FormatException ? "catalog_invalid" : "catalog_unavailable",
                CheckedAt = DateTimeOffset.UtcNow,
            };
        }

        return catalog;
    }

    public async Task InstallAsync(string catalogId, string version, CancellationToken cancellationToken)
    {
        await operations.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var current = await RefreshCatalogAsync(force: true, cancellationToken).ConfigureAwait(false);
            var release = current.Releases.FirstOrDefault(candidate => candidate.CatalogId == catalogId)
                ?? throw new ThemeInstallException("unknown_theme", "Theme is not in the official catalog");
            if (release.Version != version)
            {
                throw new ThemeInstallException("publication_changed", "Published version changed");
            }

            var archive = await channel.ArtifactAsync(release, cancellationToken).ConfigureAwait(false);
            var installed = installer.Install(release, archive);
            MirrorAssets(installed);
            settings.Update(themes => themes.Any(theme => theme.Name == installed.Name)
                ? themes
                : themes.Append(new ThemeSetting(installed.Name, false, new Dictionary<string, string>())).ToArray());
            CompanionLog.Write("themes.install", $"{catalogId} {version}");
        }
        finally
        {
            operations.Release();
        }
    }

    public void SetEnabled(string name, bool enabled)
    {
        var library = Library();
        var theme = library.Themes.FirstOrDefault(candidate => candidate.Name == name)
            ?? throw new ThemeInstallException("not_installed", "Theme is not installed");
        var group = catalog.Releases.FirstOrDefault(release => release.CssLoaderName == name)?.ExclusiveGroup;
        var exclusive = group is null
            ? new HashSet<string>()
            : catalog.Releases.Where(release => release.ExclusiveGroup == group && release.CssLoaderName != name)
                .Select(release => release.CssLoaderName)
                .ToHashSet(StringComparer.Ordinal);
        settings.Update(themes =>
        {
            var next = themes
                .Select(setting => enabled && exclusive.Contains(setting.Name) ? setting with { Enabled = false } : setting)
                .ToList();
            var index = next.FindIndex(setting => setting.Name == name);
            if (index < 0)
            {
                next.Add(new ThemeSetting(name, enabled, new Dictionary<string, string>()));
            }
            else
            {
                next[index] = next[index] with { Enabled = enabled };
            }

            return next;
        });
        if (enabled)
        {
            MirrorAssets(theme);
        }

        CompanionLog.Write("themes.enabled", $"{name} {enabled}");
    }

    public void SetPatch(string name, string patch, string value)
    {
        var theme = Library().Themes.FirstOrDefault(candidate => candidate.Name == name)
            ?? throw new ThemeInstallException("not_installed", "Theme is not installed");
        var declared = theme.Manifest.Patches.FirstOrDefault(candidate => candidate.Name == patch)
            ?? throw new ThemeInstallException("unknown_option", "Option does not exist");
        if (declared.Options.All(option => option.Value != value))
        {
            throw new ThemeInstallException("unknown_option", "Option value does not exist");
        }

        settings.Update(themes =>
        {
            var next = themes.ToList();
            var index = next.FindIndex(setting => setting.Name == name);
            var current = index < 0 ? new ThemeSetting(name, false, new Dictionary<string, string>()) : next[index];
            var patches = new Dictionary<string, string>(current.Patches) { [patch] = value };
            var updated = current with { Patches = patches };
            if (index < 0)
            {
                next.Add(updated);
            }
            else
            {
                next[index] = updated;
            }

            return next;
        });
        CompanionLog.Write("themes.option", $"{name} / {patch} = {value}");
    }

    public void EnableSteamDebugging()
    {
        steam.EnableDebugging();
        CompanionLog.Write("themes.debugging", "enabled");
    }

    public async Task RestartSteamAsync(CancellationToken cancellationToken)
    {
        if (!steam.DebuggingEnabled)
        {
            EnableSteamDebugging();
        }

        CompanionLog.Write("themes.restart_steam", "requested");
        await steam.RestartAsync(bigPicture: false, cancellationToken).ConfigureAwait(false);
    }

    public ThemeEngineInputs EngineInputs()
    {
        var library = Library();
        var stored = settings.Read();
        var enabled = stored
            .Where(setting => setting.Enabled)
            .Select(setting => (setting, theme: library.Themes.FirstOrDefault(theme => theme.Name == setting.Name)))
            .Where(pair => pair.theme is not null)
            .Select(pair => new ThemeSelection(pair.theme!, pair.setting.Patches))
            .ToArray();
        foreach (var selection in enabled)
        {
            MirrorAssetsIfStale(selection.Theme);
        }

        var extensions = enabled
            .Where(selection => selection.Theme.Marker?.Extension is not null)
            .Select(selection => (selection.Theme, source: ThemeLibrary.ReadExtension(selection.Theme)))
            .Where(pair => pair.source is not null)
            .Select(pair => new ThemeHostExtension(
                pair.Theme.Marker!.CatalogIdentity,
                pair.Theme.Name,
                pair.Theme.Manifest.Version,
                pair.Theme.Marker.Extension!.AbiVersion,
                pair.Theme.Marker.Extension.Sha256,
                pair.source!))
            .ToArray();
        return new ThemeEngineInputs(enabled, extensions, HostSnapshotJson(library, stored));
    }

    /// <summary>The <c>CssLoaderSnapshot</c> the shared theme runtime expects.</summary>
    public static string HostSnapshotJson(ThemeLibrarySnapshot library, IReadOnlyList<ThemeSetting> stored)
    {
        var themes = library.Themes.Select(theme =>
        {
            var setting = stored.FirstOrDefault(candidate => candidate.Name == theme.Name);
            return new
            {
                id = theme.Name,
                name = theme.Name,
                displayName = theme.Manifest.DisplayName,
                version = theme.Manifest.Version,
                author = theme.Manifest.Author,
                enabled = setting?.Enabled ?? false,
                patches = theme.Manifest.Patches.Select(patch => new
                {
                    name = patch.Name,
                    defaultValue = patch.DefaultValue,
                    value = patch.Resolve(setting?.Patches.GetValueOrDefault(patch.Name)).Value,
                    options = patch.Options.Select(option => option.Value).ToArray(),
                    type = patch.Type.ToString().ToLowerInvariant(),
                    rawType = patch.Type.ToString().ToLowerInvariant(),
                }).ToArray(),
            };
        });
        return JsonSerializer.Serialize(new { status = "ready", themes });
    }

    private string? ThemesCustomRoot =>
        steam.SteamPath is { } path ? Path.Combine(path, "steamui", "themes_custom") : null;

    // Steam serves /themes_custom/<theme>/... from steamui; CSS Loader links its theme folder
    // there on Linux. A copy keeps the URLs working without a link or elevation.
    private void MirrorAssets(InstalledTheme theme)
    {
        if (ThemesCustomRoot is not { } root || IsForeignLink(root))
        {
            return;
        }

        try
        {
            var target = Path.Combine(root, theme.Name);
            var staging = Path.Combine(root, $".pdc-{Guid.NewGuid():N}");
            CopyTree(theme.Directory, staging);
            if (Directory.Exists(target))
            {
                Directory.Delete(target, recursive: true);
            }

            Directory.Move(staging, target);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            CompanionLog.Write("themes.mirror_assets", exception);
        }
    }

    private void MirrorAssetsIfStale(InstalledTheme theme)
    {
        if (ThemesCustomRoot is not { } root || IsForeignLink(root))
        {
            return;
        }

        var manifest = Path.Combine(root, theme.Name, ThemeLibrary.ManifestFileName);
        try
        {
            if (!File.Exists(manifest) || ThemeManifest.Parse(File.ReadAllText(manifest)).Version != theme.Manifest.Version)
            {
                MirrorAssets(theme);
            }
        }
        catch (ThemeManifestException)
        {
            MirrorAssets(theme);
        }
    }

    // CSS Loader Desktop links steamui\themes_custom to its own theme folder; writing through that
    // link would replace the copy it manages.
    private static bool IsForeignLink(string root)
    {
        var directory = new DirectoryInfo(root);
        return directory.Exists && (directory.LinkTarget is not null || directory.Attributes.HasFlag(FileAttributes.ReparsePoint));
    }

    private static void CopyTree(string source, string destination)
    {
        foreach (var directory in Directory.EnumerateDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(Path.Combine(destination, Path.GetRelativePath(source, directory)));
        }

        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            File.Copy(file, Path.Combine(destination, Path.GetRelativePath(source, file)), overwrite: true);
        }
    }
}
