using System.Text;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// Panel's own install record kept inside the game's <c>.pdc-upscaler</c> folder, so it survives the package's private
/// data being wiped on an update and goes away with the manifest on uninstall. It is never listed in the manifest.
/// </summary>
public static class PanelInstallRecord
{
    public const string FileName = "panel-install.json";
    public const long MaximumBytes = 256 * 1024;

    private static readonly UTF8Encoding Utf8 = new(false);

    public static void Write(string target, StoredUpscaler stored)
    {
        var meta = Path.Combine(target, GameManifest.Folder);
        if (!Directory.Exists(meta) || (File.GetAttributes(meta) & FileAttributes.ReparsePoint) != 0)
        {
            throw new IOException("meta folder missing or a link");
        }

        var path = Path.Combine(meta, FileName);
        var temporary = Path.Combine(meta, "." + FileName + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            File.WriteAllText(temporary, PythonJson.Write(UpscalerStateStore.WriteInstall(stored)), Utf8);
            if (File.Exists(path))
            {
                File.Replace(temporary, path, null);
            }
            else
            {
                File.Move(temporary, path);
            }
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    /// <summary>Null when there is no record, it is not a regular small file, or it does not parse as an install.</summary>
    public static StoredUpscaler? Read(string target)
    {
        try
        {
            var path = Path.Combine(target, GameManifest.Folder, FileName);
            var info = new FileInfo(path);
            if (!info.Exists || info.Length > MaximumBytes || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return null;
            }

            return DataValue.Parse(File.ReadAllText(path, Utf8)) is DataObject document ? UpscalerStateStore.ReadInstall(document) : null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DataFormatException)
        {
            return null;
        }
    }
}
