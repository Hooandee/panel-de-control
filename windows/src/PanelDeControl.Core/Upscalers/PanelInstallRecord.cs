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

    /// <param name="receipt">The image controls' receipt, kept beside the install so a restore still works after Panel is reinstalled.</param>
    public static void Write(string target, StoredUpscaler stored, ImageSettingsReceipt? receipt = null)
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
            var document = (DataObject)UpscalerStateStore.WriteInstall(stored);
            if (receipt is not null)
            {
                document = new DataObject(document.Members.Append(new KeyValuePair<string, DataValue>("image_settings", UpscalerStateStore.WriteReceipt(receipt))).ToList());
            }

            File.WriteAllText(temporary, PythonJson.Write(document), Utf8);
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

    /// <summary>The image controls' receipt saved with the record, if any.</summary>
    public static ImageSettingsReceipt? ReadReceipt(string target) =>
        Document(target) is { } document ? UpscalerStateStore.ReadReceipt(document.Get("image_settings")) : null;

    /// <summary>Null when there is no record, it is not a regular small file, or it does not parse as an install.</summary>
    public static StoredUpscaler? Read(string target) => Document(target) is { } document ? UpscalerStateStore.ReadInstall(document) : null;

    private static DataObject? Document(string target)
    {
        try
        {
            var path = Path.Combine(target, GameManifest.Folder, FileName);
            var info = new FileInfo(path);
            if (!info.Exists || info.Length > MaximumBytes || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                return null;
            }

            return DataValue.Parse(File.ReadAllText(path, Utf8)) as DataObject;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DataFormatException)
        {
            return null;
        }
    }
}
