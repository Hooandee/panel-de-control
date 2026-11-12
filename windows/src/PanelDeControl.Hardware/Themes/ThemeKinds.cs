namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// On-screen keyboard themes dress only Steam's keyboard: they live next to a Home theme and only one of them is on at
/// a time. The catalog marks them with the <c>keyboard</c> exclusive group; an installed one also says so in its
/// manifest's <c>target</c>, which covers early and hand-installed copies the catalog does not list.
/// </summary>
public static class ThemeKinds
{
    public const string KeyboardGroup = "keyboard";

    public static bool IsKeyboard(InstalledTheme? theme, string? exclusiveGroup) =>
        exclusiveGroup == KeyboardGroup || theme?.Manifest.IsKeyboard == true;
}
