namespace PanelDeControl.Hardware;

public static class CompanionLog
{
    private const long MaximumBytes = 256 * 1024;

    public static string FilePath { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "companion.log");

    public static void Write(string step, Exception exception)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            if (File.Exists(FilePath) && new FileInfo(FilePath).Length > MaximumBytes)
            {
                File.Delete(FilePath);
            }

            File.AppendAllText(
                FilePath,
                $"[{DateTimeOffset.Now:O}] {step} {exception}{Environment.NewLine}");
        }
        catch
        {
        }
    }
}
