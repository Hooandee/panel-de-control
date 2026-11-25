using System.Runtime.InteropServices;
using System.Text;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// <c>%LOCALAPPDATA%\Packages\&lt;family&gt;\TempState</c>: what the widget sees as
/// <c>ApplicationData.Current.TemporaryFolder</c>, shared with this full-trust process.
/// </summary>
public static class PackageTempFolder
{
    private const int ErrorInsufficientBuffer = 122;

    /// <summary>Outside a package (development runs) early imports have nowhere to come from.</summary>
    public static string ResolveOrUnavailable()
    {
        try
        {
            return Resolve();
        }
        catch (InvalidOperationException exception)
        {
            CompanionLog.Write("themes.early_import_folder", exception);
            return Path.Combine(Path.GetTempPath(), "PanelDeControl-no-package");
        }
    }

    public static string Resolve()
    {
        var length = 0;
        if (GetCurrentPackageFamilyName(ref length, null) != ErrorInsufficientBuffer)
        {
            throw new InvalidOperationException("The companion is not running inside its package");
        }

        var family = new StringBuilder(length);
        if (GetCurrentPackageFamilyName(ref length, family) != 0)
        {
            throw new InvalidOperationException("The package family name is unavailable");
        }

        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Packages",
            family.ToString(),
            "TempState");
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetCurrentPackageFamilyName(ref int packageFamilyNameLength, StringBuilder? packageFamilyName);
}
