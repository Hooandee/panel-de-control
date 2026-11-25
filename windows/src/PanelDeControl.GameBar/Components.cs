using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

internal static class Components
{
    public static void MarkChoice(Button chip, bool active)
    {
        chip.Background = active ? Resource("PdcAccentSoftBrush") : Resource("PdcTransparentBrush");
        chip.BorderBrush = Resource("PdcAccentRimBrush");
        chip.BorderThickness = new Thickness(active ? 1 : 0);
        chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
        chip.Foreground = Resource(active ? "PdcChoiceTextBrush" : "PdcTextPrimaryBrush");
    }

    /// <summary>
    /// Selected and idle look of a section tab. In the Game Bar bar the selection is the sliding indicator, so the
    /// tab itself only changes its text; in the desktop side menu the selected entry is filled.
    /// </summary>
    public static void MarkTab(Button tab, bool selected, bool sideMenu, Brush fill, Brush rim)
    {
        tab.Background = selected && sideMenu ? fill : Resource("PdcTransparentBrush");
        tab.BorderBrush = rim;
        tab.BorderThickness = new Thickness(selected && sideMenu ? 1 : 0);
        tab.Foreground = Resource(
            !selected ? "PdcTextMutedBrush"
            : sideMenu && Skins.Current == PdcSkin.Editorial ? "PdcTextPrimaryBrush"
            : "PdcTabSelectedTextBrush");
    }

    public static void MarkSwatch(Button swatch, bool selected) => swatch.BorderThickness = new Thickness(selected ? 2 : 0);

    /// <summary>
    /// Controls inside a read-only host stay disabled but keep near-full opacity: they show a value, not a fault.
    /// </summary>
    public static void MarkReadOnly(FrameworkElement host) =>
        host.Resources["PdcDisabledOpacity"] = Application.Current.Resources["PdcReadOnlyOpacity"];

    public static Style Style(string key) => (Style)Application.Current.Resources[key];

    private static Brush Resource(string key) => (Brush)Application.Current.Resources[key];
}
