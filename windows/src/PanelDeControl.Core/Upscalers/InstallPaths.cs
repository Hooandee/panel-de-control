namespace PanelDeControl.Core.Upscalers;

internal static class InstallPaths
{
    public static bool IsLink(string path)
    {
        try
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return false;
        }
    }

    public static bool Inside(string path, string root)
    {
        var prefix = root.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal) ? root : root + Path.DirectorySeparatorChar;
        return path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase);
    }

    public static void Put(List<KeyValuePair<string, string>> sources, string relative, string path)
    {
        var index = sources.FindIndex(pair => GameManifest.PathComparer.Equals(pair.Key, relative));
        if (index >= 0)
        {
            sources[index] = new KeyValuePair<string, string>(relative, path);
        }
        else
        {
            sources.Add(new KeyValuePair<string, string>(relative, path));
        }
    }
}
