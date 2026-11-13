namespace PanelDeControl.Core.Upscalers;

/// <summary>The files of an unpacked OptiScaler release, keyed by where they go relative to the exe folder.</summary>
public static class OptiScalerRelease
{
    private static readonly string[] Junk = { "setup_linux.sh", "setup_windows.bat" };

    public static Dictionary<string, string> Sources(string archive, int generation)
    {
        var sources = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var file in Directory.GetFiles(archive))
        {
            var name = Path.GetFileName(file);
            if (!Junk.Contains(name) && !name.StartsWith("!", StringComparison.Ordinal) && !name.StartsWith(".", StringComparison.Ordinal))
            {
                sources[name] = file;
            }
        }
        var folders = generation >= 10 ? new[] { "OptiScaler" } : new[] { "D3D12_Optiscaler" };
        foreach (var folder in folders)
        {
            var path = Path.Combine(archive, folder);
            if (!Directory.Exists(path))
            {
                continue;
            }
            foreach (var file in Directory.GetFiles(path, "*", SearchOption.AllDirectories))
            {
                if (!string.Equals(Path.GetExtension(file), ".bat", StringComparison.OrdinalIgnoreCase))
                {
                    sources[file.Substring(archive.Length + 1).Replace(Path.DirectorySeparatorChar, '/')] = file;
                }
            }
        }
        return sources;
    }
}
