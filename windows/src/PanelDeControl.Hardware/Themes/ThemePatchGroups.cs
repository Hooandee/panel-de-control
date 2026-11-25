using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Same option groups and order as the Linux theme details (<c>src/themes/patchGroups.ts</c>), so a
/// theme reads the same in Decky and in the widget.
/// </summary>
public static class ThemePatchGroups
{
    public static readonly IReadOnlyList<string> Order = new[]
    {
        "appearance", "grid", "animations", "performance", "compatibility", "sections", "extra",
    };

    private const string SectionPrefix = "Estilizar ";

    private static readonly (string Group, Regex Pattern)[] Matchers =
    {
        ("grid", new Regex("grid|parrilla|cover|portada|carátula|caratula|column|row|fila|library|biblioteca|card|tarjeta", RegexOptions.CultureInvariant)),
        ("animations", new Regex("anim|motion|movimiento|flota|float|transition|transición|transicion|spring|parallax", RegexOptions.CultureInvariant)),
        ("performance", new Regex("performance|rendimiento|quality|calidad|blur|desenfoque|effect|efecto|fps|budget", RegexOptions.CultureInvariant)),
        ("compatibility", new Regex("compat|navigation|navegación|navegacion|fallback|legacy|steam|decky", RegexOptions.CultureInvariant)),
    };

    public static bool IsHooandee(string? catalogId) => catalogId?.StartsWith("hooandee-", StringComparison.Ordinal) == true;

    /// <summary>The group of an option, or null when a Hooandee theme's title row is not shown.</summary>
    public static string? GroupOf(ThemePatch patch, string? catalogId, PanelThemeMarker? marker)
    {
        var hooandee = IsHooandee(catalogId);
        if (hooandee && patch.Type == ThemePatchType.None)
        {
            return null;
        }

        if (marker?.Labels.TryGetValue(patch.Name, out var label) == true && label.Extra)
        {
            return "extra";
        }

        if (hooandee && patch.Type == ThemePatchType.Checkbox && patch.Name.StartsWith(SectionPrefix, StringComparison.Ordinal))
        {
            return "sections";
        }

        var name = patch.Name.ToLowerInvariant();
        return Matchers.FirstOrDefault(matcher => matcher.Pattern.IsMatch(name)).Group ?? "appearance";
    }
}
