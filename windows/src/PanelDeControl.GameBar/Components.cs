using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

/// <summary>Behaviour shared by catalog components that code builds or updates (see Theme/PdcComponents.xaml).</summary>
internal static class Components
{
    /// <summary>The one selected look for every segmented choice: accent glass with a lit rim.</summary>
    public static void MarkChoice(Button chip, bool active)
    {
        chip.Background = active ? Brush("PdcAccentSoftBrush") : Brush("PdcTransparentBrush");
        chip.BorderBrush = Brush("PdcAccentRimBrush");
        chip.BorderThickness = new Thickness(active ? 1 : 0);
        chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
    }

    public static Brush Brush(string key) => (Brush)Application.Current.Resources[key];

    public static Style Style(string key) => (Style)Application.Current.Resources[key];
}
