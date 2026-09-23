using System;
using System.IO;
using Windows.Storage;

namespace PanelDeControl.GameBar;

internal static class CrashLog
{
    private const string FileName = "crash.log";
    private const long MaximumBytes = 256 * 1024;

    public static void Write(string context, Exception? exception, string? message = null)
    {
        try
        {
            var path = Path.Combine(ApplicationData.Current.LocalFolder.Path, FileName);
            if (File.Exists(path) && new FileInfo(path).Length > MaximumBytes)
            {
                File.Delete(path);
            }

            File.AppendAllText(
                path,
                $"[{DateTimeOffset.Now:O}] {context}: {message}{Environment.NewLine}{exception}{Environment.NewLine}{Environment.NewLine}");
        }
        catch
        {
        }
    }
}
