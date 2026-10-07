namespace PanelDeControl.Hardware.Themes;

public sealed record BrokenTheme(string FolderName, string Reason);

public sealed record ThemeLibrarySnapshot(IReadOnlyList<InstalledTheme> Themes, IReadOnlyList<BrokenTheme> Broken);

/// <summary>
/// Installed themes under <c>%LOCALAPPDATA%\PanelDeControl\Themes</c>, one CSS Loader folder each.
/// </summary>
public static class ThemeLibrary
{
    public const string ManifestFileName = "theme.json";
    public const long MaximumManifestBytes = 256 * 1024;

    public static string DefaultRoot { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "Themes");

    public static ThemeLibrarySnapshot Scan(string root)
    {
        var themes = new List<InstalledTheme>();
        var broken = new List<BrokenTheme>();
        if (!Directory.Exists(root))
        {
            return new ThemeLibrarySnapshot(themes, broken);
        }

        foreach (var directory in Directory.EnumerateDirectories(root).OrderBy(path => path, StringComparer.Ordinal))
        {
            var folder = Path.GetFileName(directory);
            if (folder.StartsWith('.'))
            {
                continue;
            }

            try
            {
                var theme = Load(directory);
                if (theme is null)
                {
                    broken.Add(new BrokenTheme(folder, "missing_manifest"));
                }
                else if (theme.Name != folder)
                {
                    broken.Add(new BrokenTheme(folder, "identity_mismatch"));
                }
                else
                {
                    themes.Add(theme);
                }
            }
            catch (ThemeManifestException)
            {
                broken.Add(new BrokenTheme(folder, "invalid_manifest"));
            }
            catch (IOException)
            {
                broken.Add(new BrokenTheme(folder, "unreadable"));
            }
        }

        return new ThemeLibrarySnapshot(themes, broken);
    }

    public static InstalledTheme? Load(string directory)
    {
        var manifestPath = Path.Combine(directory, ManifestFileName);
        if (!File.Exists(manifestPath))
        {
            return null;
        }

        if (new FileInfo(manifestPath).Length > MaximumManifestBytes)
        {
            throw new ThemeManifestException("theme.json is too large");
        }

        var manifest = ThemeManifest.Parse(File.ReadAllText(manifestPath));
        var markerPath = Path.Combine(directory, PanelThemeMarker.FileName);
        PanelThemeMarker? marker = null;
        if (File.Exists(markerPath))
        {
            if (new FileInfo(markerPath).Length > MaximumManifestBytes)
            {
                throw new ThemeManifestException("panel-theme.json is too large");
            }

            marker = PanelThemeMarker.Parse(File.ReadAllText(markerPath));
        }

        var extensionPath = Path.Combine(directory, PanelThemeMarker.ExtensionEntrypoint);
        if (marker?.Extension is null && File.Exists(extensionPath))
        {
            throw new ThemeManifestException("Theme extension is not declared");
        }

        if (marker?.Extension is not null
            && (!File.Exists(extensionPath) || !marker.ExtensionMatches(File.ReadAllBytes(extensionPath))))
        {
            throw new ThemeManifestException("Theme extension does not match its declaration");
        }

        return new InstalledTheme(manifest, marker, directory);
    }

    public static string? ReadExtension(InstalledTheme theme)
    {
        if (theme.Marker?.Extension is null)
        {
            return null;
        }

        var bytes = File.ReadAllBytes(Path.Combine(theme.Directory, PanelThemeMarker.ExtensionEntrypoint));
        return theme.Marker.ExtensionMatches(bytes) ? System.Text.Encoding.UTF8.GetString(bytes) : null;
    }
}
