namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// The shared theme runtime host (<c>src/windowsThemeHost</c>) compiled to one script and embedded at
/// build time, so it always matches this companion.
/// </summary>
public static class SteamThemeHostBundle
{
    private const string ResourceName = "PanelDeControl.Hardware.Themes.steam-theme-host.js";

    private static readonly Lazy<string> Source = new(() =>
    {
        using var stream = typeof(SteamThemeHostBundle).Assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException("The theme host bundle is missing from the build");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    });

    public static string Read() => Source.Value;
}
