namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// A game folder that moved to another Steam library since the install: the paths Panel stored point at the old
/// place, and removal finds Panel's files under the folder the game has now (<c>_relocated</c> in <c>py_modules/upscalers/service.py</c>).
/// </summary>
public static class InstallRelocation
{
    /// <summary>The install with its stored folders mapped under <paramref name="root"/>; the object is changed in place.</summary>
    public static InstalledUpscaler Apply(InstalledUpscaler install, string root)
    {
        var oldTarget = install.Target;
        if (oldTarget.Length == 0 || root.Length == 0)
        {
            return install;
        }

        install.Target = Relocated(oldTarget, oldTarget, root);
        install.ExeFolder = Relocated(install.ExeFolder, oldTarget, root);
        install.Log = Relocated(install.Log, oldTarget, root);
        install.HelixFile = Relocated(install.HelixFile, oldTarget, root);
        return install;
    }

    /// <summary><paramref name="path"/> under the game's current folder when it is a path inside the old one and the file is there now.</summary>
    public static string Relocated(string path, string oldTarget, string root)
    {
        if (path.Length == 0)
        {
            return path;
        }

        var current = Normalize(root);
        var name = Path.GetFileName(current);
        var target = Normalize(oldTarget);
        var ancestors = new List<string>();
        for (var folder = target; folder.Length > 0; folder = Path.GetDirectoryName(folder) ?? "")
        {
            if (string.Equals(Path.GetFileName(folder), name, StringComparison.OrdinalIgnoreCase))
            {
                ancestors.Add(folder);
            }
        }

        var game = ancestors.LastOrDefault(folder => string.Equals(Path.GetFileName(Path.GetDirectoryName(folder) ?? ""), "common", StringComparison.OrdinalIgnoreCase))
            ?? ancestors.LastOrDefault();
        var full = Normalize(path);
        if (game is null || !Inside(full, game))
        {
            return path;
        }

        var moved = full.Length == game.Length ? current : Path.Combine(current, full.Substring(game.Length + 1));
        return Exists(moved) || !Exists(full) ? moved : path;
    }

    private static bool Inside(string path, string folder) =>
        string.Equals(path, folder, StringComparison.OrdinalIgnoreCase)
        || path.StartsWith(folder + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);

    private static bool Exists(string path) => File.Exists(path) || Directory.Exists(path);

    private static string Normalize(string path)
    {
        try
        {
            return Path.GetFullPath(path.Replace('/', Path.DirectorySeparatorChar)).TrimEnd(Path.DirectorySeparatorChar);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return "";
        }
    }
}

/// <summary>The executable a user picked for a game, held to what Linux accepts: a real <c>.exe</c> inside the game folder.</summary>
public static class ExeOverride
{
    /// <summary>The path relative to <paramref name="root"/>, '/'-separated, or null when it is not an <c>.exe</c> under it (lexically; the file is checked by the caller).</summary>
    public static string? Relative(string root, string exe)
    {
        if (exe.Length == 0 || exe.Any(char.IsControl))
        {
            return null;
        }

        string rootFull;
        string full;
        try
        {
            rootFull = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            full = Path.GetFullPath(Path.Combine(rootFull, exe.Replace('/', Path.DirectorySeparatorChar)));
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return null;
        }

        if (!full.StartsWith(rootFull, StringComparison.OrdinalIgnoreCase) || full.Length == rootFull.Length
            || !full.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        return full.Substring(rootFull.Length).Replace(Path.DirectorySeparatorChar, '/');
    }
}
