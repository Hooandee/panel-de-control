using PanelDeControl.Core.Themes;

namespace PanelDeControl.Hardware.Themes;

public static class ThemesResponseBuilder
{
    public static ThemesResponse Build(
        ThemeCatalogState catalog,
        ThemeLibrarySnapshot library,
        IReadOnlyList<ThemeSetting> settings,
        ThemeEngineStatus engine,
        ThemesResponseStatus status = ThemesResponseStatus.Ok,
        string? errorCode = null)
    {
        var entries = new List<ThemeEntry>();
        var names = catalog.Releases.Select(release => release.CssLoaderName)
            .Concat(library.Themes.Select(theme => theme.Name))
            .Concat(library.Broken.Select(broken => broken.FolderName))
            .Distinct(StringComparer.Ordinal);
        foreach (var name in names)
        {
            var release = catalog.Releases.FirstOrDefault(candidate => candidate.CssLoaderName == name);
            var theme = library.Themes.FirstOrDefault(candidate => candidate.Name == name);
            var broken = library.Broken.FirstOrDefault(candidate => candidate.FolderName == name);
            var setting = settings.FirstOrDefault(candidate => candidate.Name == name);
            var enabled = theme is not null && setting?.Enabled == true;
            var application = enabled && engine.Themes.TryGetValue(name, out var applied) ? applied : null;
            entries.Add(new ThemeEntry
            {
                CatalogId = theme?.Marker?.CatalogIdentity ?? release?.CatalogId,
                Name = name,
                DisplayName = release is not null
                    ? Texts(release.DisplayName)
                    : theme is not null ? new[] { new LocalizedText("en", theme.Manifest.DisplayName) } : null,
                Description = release is not null ? Texts(release.Description) : null,
                InstalledVersion = theme?.Manifest.Version,
                PublishedVersion = release?.Version,
                Enabled = enabled,
                Broken = broken?.Reason,
                PagesExpected = application?.PagesExpected ?? 0,
                PagesApplied = application?.PagesApplied ?? 0,
                RuntimeExpected = application?.RuntimeExpected ?? false,
                RuntimeMounted = application?.RuntimeMounted ?? false,
                Options = theme is null ? null : Options(theme, setting).ToArray(),
            });
        }

        return new ThemesResponse
        {
            Status = status,
            ErrorCode = errorCode,
            Connection = engine.Connection switch
            {
                SteamThemeConnection.SteamNotInstalled => ThemesConnection.SteamNotInstalled,
                SteamThemeConnection.DebuggingOff => ThemesConnection.DebuggingOff,
                SteamThemeConnection.SteamNotRunning => ThemesConnection.SteamNotRunning,
                SteamThemeConnection.RestartRequired => ThemesConnection.RestartRequired,
                SteamThemeConnection.WaitingForBigPicture => ThemesConnection.WaitingForBigPicture,
                _ => ThemesConnection.Connected,
            },
            CatalogError = catalog.ErrorCode,
            Themes = entries.ToArray(),
            RuntimeErrors = engine.Host.Errors.Count == 0 ? null : engine.Host.Errors.ToArray(),
        };
    }

    private static IEnumerable<ThemeOption> Options(InstalledTheme theme, ThemeSetting? setting)
    {
        foreach (var patch in theme.Manifest.Patches)
        {
            ThemeManifestLabels(theme, patch.Name, out var name, out var values);
            var value = patch.Resolve(setting?.Patches.GetValueOrDefault(patch.Name)).Value;
            yield return new ThemeOption(
                patch.Name,
                name.Count > 0 ? name : new[] { new LocalizedText("en", patch.Name) },
                patch.Type.ToString().ToLowerInvariant(),
                value,
                patch.DefaultValue,
                patch.Options.Select(option => new ThemeOptionValue(
                    option.Value,
                    values.TryGetValue(option.Value, out var label) ? label : Array.Empty<LocalizedText>())).ToArray());
        }
    }

    private static void ThemeManifestLabels(
        InstalledTheme theme,
        string patch,
        out IReadOnlyList<LocalizedText> name,
        out IReadOnlyDictionary<string, IReadOnlyList<LocalizedText>> values)
    {
        if (theme.Marker?.Labels.TryGetValue(patch, out var label) == true)
        {
            name = Texts(label.Name);
            values = label.Values.ToDictionary(pair => pair.Key, pair => (IReadOnlyList<LocalizedText>)Texts(pair.Value), StringComparer.Ordinal);
            return;
        }

        name = Array.Empty<LocalizedText>();
        values = new Dictionary<string, IReadOnlyList<LocalizedText>>();
    }

    private static LocalizedText[] Texts(IReadOnlyDictionary<string, string> text) =>
        text.Select(pair => new LocalizedText(pair.Key, pair.Value)).ToArray();
}
