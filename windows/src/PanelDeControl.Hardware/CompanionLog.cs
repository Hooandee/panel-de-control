namespace PanelDeControl.Hardware;

public static class CompanionLog
{
    private const long MaximumBytes = 256 * 1024;

    public static string FilePath { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PanelDeControl",
        "companion.log");

    public static void Write(string step, Exception exception) => Append($"{step} {exception}");

    public static void Write(string step, string detail) => Append($"{step} {detail}");

    private static void Append(string entry)
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
                $"[{DateTimeOffset.Now:O}] {entry}{Environment.NewLine}");
        }
        catch
        {
        }
    }
}
