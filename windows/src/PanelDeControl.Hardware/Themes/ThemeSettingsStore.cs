using System.Text.Json;
using System.Text.Json.Serialization;

namespace PanelDeControl.Hardware.Themes;

public sealed record ThemeSetting(string Name, bool Enabled, IReadOnlyDictionary<string, string> Patches);

/// <summary>
/// Which themes are on, in application order, and the chosen value of every option. Writes go
/// through a temporary file so a crash never leaves half a settings file.
/// </summary>
public sealed class ThemeSettingsStore
{
    public const string FileName = "settings.json";
    private const long MaximumBytes = 256 * 1024;

    private readonly string path;
    private readonly object gate = new();

    public ThemeSettingsStore(string libraryRoot)
    {
        path = Path.Combine(libraryRoot, FileName);
    }

    public IReadOnlyList<ThemeSetting> Read()
    {
        lock (gate)
        {
            try
            {
                if (!File.Exists(path) || new FileInfo(path).Length > MaximumBytes)
                {
                    return Array.Empty<ThemeSetting>();
                }

                var document = JsonSerializer.Deserialize<SettingsDocument>(File.ReadAllText(path));
                return document?.Themes?
                    .Where(theme => theme.Name is { } name && ThemeManifest.IsSafeName(name))
                    .GroupBy(theme => theme.Name!, StringComparer.Ordinal)
                    .Select(group => group.First())
                    .Select(theme => new ThemeSetting(
                        theme.Name!,
                        theme.Enabled,
                        theme.Patches ?? new Dictionary<string, string>()))
                    .ToArray()
                    ?? Array.Empty<ThemeSetting>();
            }
            catch (Exception exception) when (exception is JsonException or IOException or UnauthorizedAccessException)
            {
                CompanionLog.Write("themes.settings_read", exception);
                return Array.Empty<ThemeSetting>();
            }
        }
    }

    public void Write(IReadOnlyList<ThemeSetting> themes)
    {
        lock (gate)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var document = new SettingsDocument
            {
                Themes = themes.Select(theme => new SettingsTheme
                {
                    Name = theme.Name,
                    Enabled = theme.Enabled,
                    Patches = new Dictionary<string, string>(theme.Patches),
                }).ToList(),
            };
            var temporary = path + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(document, new JsonSerializerOptions { WriteIndented = true }));
            File.Move(temporary, path, overwrite: true);
        }
    }

    public IReadOnlyList<ThemeSetting> Update(Func<IReadOnlyList<ThemeSetting>, IReadOnlyList<ThemeSetting>> change)
    {
        lock (gate)
        {
            var next = change(Read());
            Write(next);
            return next;
        }
    }

    private sealed class SettingsDocument
    {
        [JsonPropertyName("schemaVersion")]
        public int SchemaVersion { get; set; } = 1;

        [JsonPropertyName("themes")]
        public List<SettingsTheme>? Themes { get; set; }
    }

    private sealed class SettingsTheme
    {
        [JsonPropertyName("name")]
        public string? Name { get; set; }

        [JsonPropertyName("enabled")]
        public bool Enabled { get; set; }

        [JsonPropertyName("patches")]
        public Dictionary<string, string>? Patches { get; set; }
    }
}
