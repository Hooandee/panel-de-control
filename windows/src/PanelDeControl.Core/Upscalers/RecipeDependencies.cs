using System.Text;
using PanelDeControl.Core.Data;
using static PanelDeControl.Core.Upscalers.InstallPaths;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// A curated recipe's dependencies and configuration for Windows, as <c>py_modules/upscalers/auto_recipes.py</c> reads them
/// on Linux. Panel installs the <c>game_files</c> packages and edits the configuration; a <c>windows_redist</c> is only
/// reported (<see cref="RecipeDependencyPlan"/>) and never stops an install, and the Proton dependencies belong to Linux.
/// </summary>
public sealed class AutomaticRecipe
{
    private const string Platform = "windows";
    private const string Bom = "\uFEFF";
    private const int MaximumBytes = 1024 * 1024;
    private static readonly UTF8Encoding Strict = new(false, true);
    private static readonly UTF8Encoding Utf8 = new(false);

    private readonly RecipeCatalog _catalog;
    private readonly IReadOnlyList<RecipeDependency> _order;
    private IReadOnlyList<UpscalerAsset>? _assets;

    private AutomaticRecipe(RecipeCatalog catalog, GameRecipe recipe, IReadOnlyList<RecipeDependency> order)
    {
        _catalog = catalog;
        Recipe = recipe;
        _order = order;
    }

    public GameRecipe Recipe { get; }

    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Configuration => Recipe.Configuration;

    public IReadOnlyList<string> Dependencies => Recipe.Dependencies;

    /// <summary>Null when the recipe has no dependencies; throws <c>recipe_unsupported</c> when Windows cannot satisfy them.</summary>
    public static AutomaticRecipe? Plan(RecipeCatalog? catalog, GameRecipe? recipe)
    {
        if (recipe is null || recipe.Dependencies.Count == 0)
        {
            return null;
        }
        if (catalog is null)
        {
            throw new UpscalerException("recipe_unsupported");
        }
        IReadOnlyList<RecipeDependency> order;
        try
        {
            order = catalog.DependencyOrder(recipe.Dependencies, Platform);
        }
        catch (DataFormatException)
        {
            throw new UpscalerException("recipe_unsupported");
        }
        if (order.Any(dependency => dependency.Kind == "game_files" && !catalog.Assets.ContainsKey(dependency.Asset ?? "")))
        {
            throw new UpscalerException("recipe_unsupported");
        }
        return new AutomaticRecipe(catalog, recipe, order);
    }

    public static bool Installable(RecipeCatalog? catalog, GameRecipe recipe)
    {
        try
        {
            Plan(catalog, recipe);
            return true;
        }
        catch (UpscalerException)
        {
            return false;
        }
    }

    /// <summary>The dependencies only the user can download, in install order.</summary>
    public IReadOnlyList<RecipeDependency> UserFileDependencies => _order.Where(dependency => dependency.Kind == "user_files").ToList();

    /// <summary>Every destination the dependencies place beside the exe.</summary>
    public IEnumerable<string> PlacedFiles => _order.SelectMany(dependency => dependency.Files.Keys);

    /// <summary>The packages to download and unpack before the game is touched.</summary>
    public IReadOnlyList<UpscalerAsset> Assets()
    {
        if (_assets is null)
        {
            var result = new Dictionary<string, UpscalerAsset>(StringComparer.Ordinal);
            foreach (var dependency in _order.Where(dependency => dependency.Kind == "game_files"))
            {
                var spec = _catalog.Assets[dependency.Asset!];
                result[spec.Id] = new UpscalerAsset(spec.Id, spec.FileName, spec.Sha256, spec.Size, new[] { spec.Url }, true, null, 9);
            }
            _assets = result.Values.ToList();
        }
        return _assets;
    }

    /// <summary>Destination beside the exe and the unpacked file it comes from, in install order.</summary>
    /// <param name="userFiles">The stored copies of what the user brought; a dependency they have not brought yet adds nothing and the rest installs.</param>
    public IReadOnlyList<KeyValuePair<string, string>> Sources(IReadOnlyDictionary<string, string> paths,
        Func<RecipeDependency, IReadOnlyDictionary<string, string>>? userFiles = null)
    {
        var result = new List<KeyValuePair<string, string>>();
        foreach (var dependency in _order.Where(dependency => dependency.Kind is "game_files" or "user_files"))
        {
            if (dependency.Kind == "user_files")
            {
                foreach (var file in userFiles?.Invoke(dependency) ?? new Dictionary<string, string>())
                {
                    if (result.Any(pair => GameManifest.PathComparer.Equals(pair.Key, file.Key)))
                    {
                        throw new UpscalerException("recipe_files_invalid");
                    }
                    result.Add(file);
                }
                continue;
            }

            var root = Path.GetFullPath(paths[dependency.Asset!]);
            foreach (var file in dependency.Files)
            {
                var source = Path.GetFullPath(Path.Combine(root, file.Value.Replace('/', Path.DirectorySeparatorChar)));
                if (!Plain(root, source) || result.Any(pair => GameManifest.PathComparer.Equals(pair.Key, file.Key)))
                {
                    throw new UpscalerException("recipe_files_invalid");
                }
                result.Add(new KeyValuePair<string, string>(file.Key, source));
            }
        }
        return result;
    }

    /// <summary>The recipe's configuration files as they will look, written into <paramref name="directory"/>; the game is not touched.</summary>
    public IReadOnlyList<KeyValuePair<string, string>> ConfiguredSources(string target, string directory)
    {
        if (Configuration.Count == 0)
        {
            return Array.Empty<KeyValuePair<string, string>>();
        }
        if (IsLink(target) || IsLink(directory) || !Directory.Exists(target) || !Directory.Exists(directory))
        {
            throw new UpscalerException("recipe_files_invalid");
        }
        var prepared = new List<KeyValuePair<string, string>>();
        foreach (var file in Configuration)
        {
            if (file.Key != "ReShade.ini" || file.Value.Count == 0 || file.Value.Any(change => !RecipeCatalog.AllowsConfiguration(file.Key, change.Key, change.Value)))
            {
                throw new UpscalerException("recipe_unsupported");
            }
            var source = Path.Combine(target, file.Key);
            if (IsLink(source))
            {
                throw new UpscalerException("recipe_files_invalid");
            }
            try
            {
                var text = "";
                if (File.Exists(source) || Directory.Exists(source))
                {
                    if (!File.Exists(source) || new FileInfo(source).Length > MaximumBytes)
                    {
                        throw new UpscalerException("recipe_files_invalid");
                    }
                    text = Strict.GetString(File.ReadAllBytes(source));
                }
                prepared.Add(new KeyValuePair<string, string>(file.Key, ConfiguredText(text, file.Value)));
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
            {
                throw new UpscalerException("recipe_files_invalid");
            }
        }
        var result = new List<KeyValuePair<string, string>>();
        foreach (var file in prepared)
        {
            var destination = Path.Combine(directory, file.Key);
            if (File.Exists(destination) || Directory.Exists(destination) || IsLink(destination))
            {
                throw new UpscalerException("recipe_files_invalid");
            }
            try
            {
                File.WriteAllBytes(destination, Utf8.GetBytes(file.Value));
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                throw new UpscalerException("recipe_files_invalid");
            }
            result.Add(new KeyValuePair<string, string>(file.Key, destination));
        }
        return result;
    }

    /// <summary>
    /// Takes the keys Panel set out of a configuration file the game rewrote since: each goes back to the value in
    /// <paramref name="backup"/> (the game's own copy) or is removed, and only while it still holds what Panel wrote.
    /// </summary>
    public static void RestoreConfiguration(string path, string backup, IReadOnlyDictionary<string, string> changes)
    {
        if (IsLink(path) || IsLink(backup))
        {
            throw new UpscalerException("recipe_files_invalid");
        }
        string text;
        var original = "";
        try
        {
            text = Read(path);
            if (File.Exists(backup))
            {
                original = Read(backup);
            }
        }
        catch (ArgumentException)
        {
            throw new UpscalerException("recipe_files_invalid");
        }
        var bom = text.StartsWith(Bom, StringComparison.Ordinal) ? Bom : "";
        text = text.StartsWith(Bom, StringComparison.Ordinal) ? text.Substring(1) : text;
        original = original.StartsWith(Bom, StringComparison.Ordinal) ? original.Substring(1) : original;
        foreach (var content in new[] { text, original })
        {
            var section = "";
            var sections = new HashSet<string>(StringComparer.Ordinal);
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var raw in IniText.SplitKeepingEnds(content))
            {
                var line = raw.TrimEnd('\r', '\n');
                var stripped = line.Trim();
                if (IsHeader(stripped))
                {
                    section = stripped.Substring(1, stripped.Length - 2);
                    if (changes.Keys.Any(key => key.StartsWith(section + ".", StringComparison.Ordinal)) && !sections.Add(section))
                    {
                        throw new UpscalerException("recipe_unsupported");
                    }
                }
                else if (line.Contains("=") && !IsComment(stripped))
                {
                    var dotted = section + "." + line.Substring(0, line.IndexOf('=')).Trim();
                    if (changes.ContainsKey(dotted) && !keys.Add(dotted))
                    {
                        throw new UpscalerException("recipe_unsupported");
                    }
                }
            }
        }
        foreach (var change in changes)
        {
            if (IniText.Read(text, change.Key) != change.Value)
            {
                continue;
            }
            var previous = IniText.Read(original, change.Key);
            if (previous is not null)
            {
                text = IniText.Apply(text, new[] { new KeyValuePair<string, string>(change.Key, previous) });
                continue;
            }
            var dot = change.Key.IndexOf('.');
            var wanted = change.Key.Substring(0, dot);
            var key = change.Key.Substring(dot + 1);
            var inside = false;
            var kept = new StringBuilder();
            foreach (var raw in IniText.SplitKeepingEnds(text))
            {
                var stripped = raw.Trim();
                if (IsHeader(stripped))
                {
                    inside = stripped.Substring(1, stripped.Length - 2) == wanted;
                }
                if (inside && raw.Contains("=") && raw.Substring(0, raw.IndexOf('=')).Trim() == key)
                {
                    continue;
                }
                kept.Append(raw);
            }
            text = kept.ToString();
        }
        File.WriteAllBytes(path, Utf8.GetBytes(bom + text));
    }

    internal static string ConfiguredText(string text, IReadOnlyDictionary<string, string> changes)
    {
        var section = "";
        var settings = new HashSet<string>(StringComparer.Ordinal);
        var luma = 0;
        foreach (var raw in IniText.SplitKeepingEnds(text.TrimStart(Bom[0])))
        {
            var line = raw.Trim();
            if (IsHeader(line))
            {
                section = line.Substring(1, line.Length - 2);
                if (section == "Luma" && ++luma > 1)
                {
                    throw new UpscalerException("recipe_unsupported");
                }
            }
            else if (line.Contains("=") && !IsComment(line))
            {
                var dotted = section + "." + line.Substring(0, line.IndexOf('=')).Trim();
                var value = line.Substring(line.IndexOf('=') + 1);
                if (dotted.ToLowerInvariant() == "install.basepath" && value.Trim().Length > 0)
                {
                    throw new UpscalerException("recipe_unsupported");
                }
                if (dotted == "Luma.SRUserType" && !settings.Add(dotted))
                {
                    throw new UpscalerException("recipe_unsupported");
                }
            }
        }
        var bom = text.StartsWith(Bom, StringComparison.Ordinal) ? Bom : "";
        return bom + IniText.Apply(text.StartsWith(Bom, StringComparison.Ordinal) ? text.Substring(1) : text, changes);
    }

    private static string Read(string path)
    {
        if (new FileInfo(path).Length > MaximumBytes)
        {
            throw new UpscalerException("recipe_files_invalid");
        }
        return Strict.GetString(File.ReadAllBytes(path));
    }

    private static bool IsHeader(string stripped) => stripped.StartsWith("[", StringComparison.Ordinal) && stripped.EndsWith("]", StringComparison.Ordinal);

    private static bool IsComment(string stripped) => stripped.StartsWith(";", StringComparison.Ordinal) || stripped.StartsWith("#", StringComparison.Ordinal);

    /// <summary>A regular file under <paramref name="root"/> reached through no link.</summary>
    private static bool Plain(string root, string source)
    {
        var prefix = root.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal) ? root : root + Path.DirectorySeparatorChar;
        if (!source.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) || !File.Exists(source))
        {
            return false;
        }
        for (var current = source; current.Length > root.Length; current = Path.GetDirectoryName(current)!)
        {
            if (IsLink(current))
            {
                return false;
            }
        }
        return true;
    }
}
