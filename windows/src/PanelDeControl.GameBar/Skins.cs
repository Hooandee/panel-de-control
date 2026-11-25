using System;
using System.Collections.Generic;
using Windows.Storage;
using Windows.UI.Xaml;

namespace PanelDeControl.GameBar;

internal enum PdcSkin
{
    Glass,
    Instrument,
    Editorial,
}

/// <summary>
/// The widget's visual skins. A skin is one token dictionary (Theme/Skins) in a fixed slot of the app resources;
/// components read it through ThemeResource, so switching only needs the page to be built again.
/// </summary>
internal static class Skins
{
    private const string SettingKey = "skin";

    // App.xaml merges PdcTokens, the skin, then PdcComponents: the skin overrides tokens and components read both.
    private const int SkinSlot = 1;
    private const int ComponentsSlot = 2;

    public static IReadOnlyList<PdcSkin> All { get; } = new[] { PdcSkin.Glass, PdcSkin.Instrument, PdcSkin.Editorial };

    public static PdcSkin Current { get; private set; } = PdcSkin.Glass;

    public static void ApplySaved()
    {
        var saved = Read();
        if (saved != PdcSkin.Glass)
        {
            Load(saved);
        }
    }

    public static void Choose(PdcSkin skin)
    {
        Load(skin);
        try
        {
            ApplicationData.Current.LocalSettings.Values[SettingKey] = skin.ToString();
        }
        catch
        {
        }
    }

    private static void Load(PdcSkin skin)
    {
        var merged = Application.Current.Resources.MergedDictionaries;
        merged[SkinSlot] = new ResourceDictionary { Source = new Uri($"ms-appx:///Theme/Skins/PdcSkin{skin}.xaml") };
        // Styles resolve their ThemeResource values when the catalog loads, so it is loaded again on the new skin.
        merged[ComponentsSlot] = new ResourceDictionary { Source = new Uri("ms-appx:///Theme/PdcComponents.xaml") };
        Current = skin;
    }

    private static PdcSkin Read()
    {
        try
        {
            return Enum.TryParse(ApplicationData.Current.LocalSettings.Values[SettingKey] as string, out PdcSkin skin)
                ? skin
                : PdcSkin.Glass;
        }
        catch
        {
            return PdcSkin.Glass;
        }
    }
}
