using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

public sealed class ThemeManifestException : Exception
{
    public ThemeManifestException(string message)
        : base(message)
    {
    }
}

public enum ThemePatchType
{
    Dropdown,
    Checkbox,
    Slider,
    None,
}

public sealed record ThemeInject(string File, IReadOnlyList<string> Targets);

public sealed record ThemePatchOption(string Value, IReadOnlyList<ThemeInject> Injects);

public sealed record ThemePatch(
    string Name,
    ThemePatchType Type,
    string DefaultValue,
    IReadOnlyList<ThemePatchOption> Options)
{
    public ThemePatchOption Resolve(string? value) =>
        Options.FirstOrDefault(option => option.Value == value)
        ?? Options.First(option => option.Value == DefaultValue);
}

/// <summary>
/// The subset of the CSS Loader manifest that Hooandee themes use. Anything outside it fails
/// closed so a theme is never half applied.
/// </summary>
public sealed class ThemeManifest
{
    public const int MaximumNameLength = 128;

    private static readonly HashSet<string> UnsupportedThemeKeys = new(StringComparer.Ordinal)
    {
        "dependencies",
        "flags",
    };

    private ThemeManifest(
        string name,
        string displayName,
        string version,
        string author,
        IReadOnlyList<ThemeInject> injects,
        IReadOnlyList<ThemePatch> patches)
    {
        Name = name;
        DisplayName = displayName;
        Version = version;
        Author = author;
        Injects = injects;
        Patches = patches;
    }

    public string Name { get; }

    public string DisplayName { get; }

    public string Version { get; }

    public string Author { get; }

    public IReadOnlyList<ThemeInject> Injects { get; }

    public IReadOnlyList<ThemePatch> Patches { get; }

    public IEnumerable<string> AllCssFiles =>
        Injects.Select(inject => inject.File)
            .Concat(Patches.SelectMany(patch => patch.Options).SelectMany(option => option.Injects).Select(inject => inject.File))
            .Distinct(StringComparer.Ordinal);

    public IReadOnlyList<ThemeInject> ActiveInjects(IReadOnlyDictionary<string, string> values)
    {
        var active = new List<ThemeInject>(Injects);
        foreach (var patch in Patches)
        {
            values.TryGetValue(patch.Name, out var value);
            active.AddRange(patch.Resolve(value).Injects);
        }

        return active;
    }

    public static ThemeManifest Parse(string json)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(json);
        }
        catch (JsonException)
        {
            throw new ThemeManifestException("theme.json is not valid JSON");
        }

        using (document)
        {
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw new ThemeManifestException("theme.json must be an object");
            }

            foreach (var property in root.EnumerateObject())
            {
                if (UnsupportedThemeKeys.Contains(property.Name))
                {
                    throw new ThemeManifestException($"Unsupported manifest key {property.Name}");
                }
            }

            var name = RequiredString(root, "name");
            if (!IsSafeName(name))
            {
                throw new ThemeManifestException("Theme name is unsafe");
            }

            var version = RequiredString(root, "version");
            var displayName = OptionalString(root, "display_name") ?? name;
            var author = OptionalString(root, "author") ?? string.Empty;
            var injects = root.TryGetProperty("inject", out var inject)
                ? ParseInjects(inject)
                : Array.Empty<ThemeInject>();
            var patches = root.TryGetProperty("patches", out var patchesElement)
                ? ParsePatches(patchesElement)
                : Array.Empty<ThemePatch>();
            return new ThemeManifest(name, displayName, version, author, injects, patches);
        }
    }

    public static bool IsSafeName(string name) =>
        name.Length > 0
        && name.Length <= MaximumNameLength
        && name == name.Trim()
        && name.IndexOfAny(new[] { '/', '\\', ':', '*', '?', '"', '<', '>', '|' }) < 0
        && !name.Any(char.IsControl)
        && name != "."
        && name != "..";

    public static bool IsSafeRelativeCssPath(string path) =>
        IsSafeRelativePath(path) && path.EndsWith(".css", StringComparison.OrdinalIgnoreCase);

    public static bool IsSafeRelativePath(string path)
    {
        if (path.Length == 0 || path.Length > 260 || path.Contains('\\') || path.Contains(':') || path.StartsWith('/'))
        {
            return false;
        }

        return path.Split('/').All(segment =>
            segment.Length > 0
            && segment != "."
            && segment != ".."
            && !segment.Any(char.IsControl));
    }

    private static IReadOnlyList<ThemeInject> ParseInjects(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            throw new ThemeManifestException("inject must be an object");
        }

        var injects = new List<ThemeInject>();
        foreach (var property in element.EnumerateObject())
        {
            if (!IsSafeRelativeCssPath(property.Name))
            {
                throw new ThemeManifestException($"Unsafe inject path {property.Name}");
            }

            if (property.Value.ValueKind != JsonValueKind.Array)
            {
                throw new ThemeManifestException("inject targets must be an array");
            }

            var targets = property.Value.EnumerateArray()
                .Select(target => target.ValueKind == JsonValueKind.String
                    ? target.GetString()!
                    : throw new ThemeManifestException("inject target must be a string"))
                .ToArray();
            if (targets.Length == 0 || targets.Any(target => target.Length == 0))
            {
                throw new ThemeManifestException("inject targets are empty");
            }

            injects.Add(new ThemeInject(property.Name, targets));
        }

        return injects;
    }

    private static IReadOnlyList<ThemePatch> ParsePatches(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            throw new ThemeManifestException("patches must be an object");
        }

        var patches = new List<ThemePatch>();
        foreach (var property in element.EnumerateObject())
        {
            var patch = property.Value;
            if (patch.ValueKind != JsonValueKind.Object || patch.TryGetProperty("components", out _))
            {
                throw new ThemeManifestException($"Unsupported patch {property.Name}");
            }

            var type = (OptionalString(patch, "type") ?? "dropdown") switch
            {
                "dropdown" => ThemePatchType.Dropdown,
                "checkbox" => ThemePatchType.Checkbox,
                "slider" => ThemePatchType.Slider,
                "none" => ThemePatchType.None,
                var other => throw new ThemeManifestException($"Unsupported patch type {other}"),
            };
            var defaultValue = RequiredString(patch, "default");
            if (!patch.TryGetProperty("values", out var values) || values.ValueKind != JsonValueKind.Object)
            {
                throw new ThemeManifestException("Patch values must be an object");
            }

            var options = values.EnumerateObject()
                .Select(option => new ThemePatchOption(option.Name, ParseInjects(option.Value)))
                .ToArray();
            if (options.All(option => option.Value != defaultValue))
            {
                throw new ThemeManifestException($"Patch {property.Name} default is not an option");
            }

            patches.Add(new ThemePatch(property.Name, type, defaultValue, options));
        }

        return patches;
    }

    private static string RequiredString(JsonElement element, string name) =>
        OptionalString(element, name) is { } value && value.Length > 0
            ? value
            : throw new ThemeManifestException($"{name} is required");

    private static string? OptionalString(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value)
            ? value.ValueKind == JsonValueKind.String
                ? value.GetString()
                : throw new ThemeManifestException($"{name} must be a string")
            : null;
}
