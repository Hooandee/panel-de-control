namespace PanelDeControl.Core.NativeKeyboard;

public static class NativeKeyboardThemes
{
    public const string Terciopelo = "terciopelo";
    public const string LoboBlanco = "lobo-blanco";

    public static bool IsValid(string? themeId) => themeId is Terciopelo or LoboBlanco;
}
