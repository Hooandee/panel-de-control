using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

internal static class Components
{
    public static void MarkChoice(Button chip, bool active)
    {
        chip.Background = active ? Brush("PdcAccentSoftBrush") : Brush("PdcTransparentBrush");
        chip.BorderBrush = Brush("PdcAccentRimBrush");
        chip.BorderThickness = new Thickness(active ? 1 : 0);
        chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
        chip.Foreground = Brush(active ? "PdcChoiceTextBrush" : "PdcTextPrimaryBrush");
    }

    /// <summary>
    /// Selected and idle look of a section tab. In the Game Bar bar the selection is the sliding indicator, so the
    /// tab itself only changes its text; in the desktop side menu the selected entry is filled.
    /// </summary>
    public static void MarkTab(Button tab, bool selected, bool sideMenu, Brush fill, Brush rim)
    {
        tab.Background = selected && sideMenu ? fill : Brush("PdcTransparentBrush");
        tab.BorderBrush = rim;
        tab.BorderThickness = new Thickness(selected && sideMenu ? 1 : 0);
        tab.Foreground = Brush(
            !selected ? "PdcTextMutedBrush"
            : sideMenu && Skins.Current == PdcSkin.Editorial ? "PdcTextPrimaryBrush"
            : "PdcTabSelectedTextBrush");
    }

    public static void MarkSwatch(Button swatch, bool selected) => swatch.BorderThickness = new Thickness(selected ? 2 : 0);

    public static Brush Brush(string key) => (Brush)Application.Current.Resources[key];

    public static Style Style(string key) => (Style)Application.Current.Resources[key];
}
