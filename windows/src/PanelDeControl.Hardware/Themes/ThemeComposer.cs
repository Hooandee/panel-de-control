namespace PanelDeControl.Hardware.Themes;

public sealed record InstalledTheme(ThemeManifest Manifest, PanelThemeMarker? Marker, string Directory)
{
    public string Name => Manifest.Name;
}

public sealed record ThemeSelection(InstalledTheme Theme, IReadOnlyDictionary<string, string> PatchValues);

public sealed record ThemeSheet(string Id, string ThemeName, string File);

public static class ThemeComposer
{
    public const string SheetIdPrefix = "pdc-theme:";

    public static string SheetId(string themeName, string file) => $"{SheetIdPrefix}{themeName}:{file}";

    /// <summary>
    /// Sheets for one Steam page, in theme order and then manifest order, deduplicated by file the
    /// way CSS Loader injects a file once per page.
    /// </summary>
    public static IReadOnlyList<ThemeSheet> SheetsFor(SteamTarget target, IReadOnlyList<ThemeSelection> enabled)
    {
        var sheets = new List<ThemeSheet>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var selection in enabled)
        {
            foreach (var inject in selection.Theme.Manifest.ActiveInjects(selection.PatchValues))
            {
                var id = SheetId(selection.Theme.Name, inject.File);
                if (!seen.Contains(id) && inject.Targets.Any(selector => ThemeTargetMatcher.Matches(target, selector)))
                {
                    seen.Add(id);
                    sheets.Add(new ThemeSheet(id, selection.Theme.Name, inject.File));
                }
            }
        }

        return sheets;
    }
}
