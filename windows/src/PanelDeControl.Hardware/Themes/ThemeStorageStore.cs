using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

public sealed record ThemeStorageSnapshot(
    IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Themes,
    IReadOnlyList<string> Unreadable);

/// <summary>
/// Durable key/value storage for theme runtimes, one file per catalog id, with the same limits as the
/// Linux backend (<c>py_modules/theme_storage.py</c>). Writes are flushed to disk before they are reported
/// as saved; a file that cannot be read is reported as unreadable, never as empty.
/// </summary>
public sealed class ThemeStorageStore
{
    public const string FolderName = ".storage";
    public const int MaximumKeys = 64;
    public const int MaximumValueBytes = 128 * 1024;
    public const int MaximumThemeBytes = 512 * 1024;
    public const int MaximumThemes = 32;
    private const int SchemaVersion = 1;

    private readonly string root;
    private readonly object gate = new();

    public ThemeStorageStore(string libraryRoot)
    {
        // A leading dot keeps the folder out of the theme library scan.
        root = Path.Combine(libraryRoot, FolderName);
    }

    private static readonly Regex SafeId = new("^[a-z0-9]+(?:-[a-z0-9]+)*$", RegexOptions.CultureInvariant);
    private static readonly Regex SafeKey = new("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", RegexOptions.CultureInvariant);

    public static bool IsSafeId(string? catalogId) => catalogId is { Length: <= 64 } && SafeId.IsMatch(catalogId);

    public static bool IsSafeKey(string? key) => key is not null && SafeKey.IsMatch(key);

    /// <summary>Saves one value; returns null when it is on disk, otherwise the reason it is not.</summary>
    public string? Set(string? catalogId, string? key, string? value)
    {
        if (!IsSafeId(catalogId))
        {
            return "invalid_theme";
        }

        if (!IsSafeKey(key))
        {
            return "invalid_key";
        }

        if (value is null || value.Contains('\0'))
        {
            return "invalid_value";
        }

        if (Encoding.UTF8.GetByteCount(value) > MaximumValueBytes)
        {
            return "too_large";
        }

        lock (gate)
        {
            var path = PathFor(catalogId!);
            Dictionary<string, string> values;
            try
            {
                values = Read(path) ?? new Dictionary<string, string>(StringComparer.Ordinal);
            }
            catch (ThemeStorageCorruptException)
            {
                // Kept beside the fresh file for support instead of blocking every later save.
                try
                {
                    File.Move(path, path + ".corrupt", overwrite: true);
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    CompanionLog.Write("themes.storage_write", exception);
                    return "write_failed";
                }

                values = new Dictionary<string, string>(StringComparer.Ordinal);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                CompanionLog.Write("themes.storage_read", exception);
                return "read_failed";
            }

            if (values.TryGetValue(key!, out var current) && current == value)
            {
                return null;
            }

            if (!File.Exists(path) && ThemeFiles().Count() >= MaximumThemes)
            {
                return "too_many_themes";
            }

            if (!values.ContainsKey(key!) && values.Count >= MaximumKeys)
            {
                return "too_many_keys";
            }

            values[key!] = value;
            var bytes = JsonSerializer.SerializeToUtf8Bytes(new StorageDocument { SchemaVersion = SchemaVersion, Values = values });
            if (bytes.Length > MaximumThemeBytes)
            {
                return "too_large";
            }

            var temporary = path + ".tmp";
            try
            {
                Directory.CreateDirectory(root);
                using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
                {
                    stream.Write(bytes);
                    stream.Flush(flushToDisk: true);
                }

                File.Move(temporary, path, overwrite: true);
                return null;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                CompanionLog.Write("themes.storage_write", exception);
                try
                {
                    File.Delete(temporary);
                }
                catch (Exception cleanup) when (cleanup is IOException or UnauthorizedAccessException)
                {
                    CompanionLog.Write("themes.storage_cleanup", cleanup);
                }

                return "write_failed";
            }
        }
    }

    public ThemeStorageSnapshot Snapshot()
    {
        lock (gate)
        {
            var themes = new Dictionary<string, IReadOnlyDictionary<string, string>>(StringComparer.Ordinal);
            var unreadable = new List<string>();
            IEnumerable<string> files;
            try
            {
                files = ThemeFiles().ToArray();
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                CompanionLog.Write("themes.storage_read", exception);
                files = Array.Empty<string>();
            }

            foreach (var file in files)
            {
                var catalogId = Path.GetFileNameWithoutExtension(file);
                try
                {
                    themes[catalogId] = Read(file) ?? new Dictionary<string, string>(StringComparer.Ordinal);
                }
                catch (Exception exception) when (exception is ThemeStorageCorruptException or IOException or UnauthorizedAccessException)
                {
                    CompanionLog.Write("themes.storage_read", exception);
                    unreadable.Add(catalogId);
                }
            }

            return new ThemeStorageSnapshot(themes, unreadable);
        }
    }

    private string PathFor(string catalogId) => Path.Combine(root, catalogId + ".json");

    private IEnumerable<string> ThemeFiles() =>
        Directory.Exists(root)
            ? Directory.EnumerateFiles(root, "*.json").Where(file => IsSafeId(Path.GetFileNameWithoutExtension(file))).OrderBy(file => file, StringComparer.Ordinal)
            : Array.Empty<string>();

    private static Dictionary<string, string>? Read(string path)
    {
        if (!File.Exists(path))
        {
            return null;
        }

        if (new FileInfo(path).Length > MaximumThemeBytes + 4096)
        {
            throw new ThemeStorageCorruptException();
        }

        StorageDocument? document;
        try
        {
            document = JsonSerializer.Deserialize<StorageDocument>(File.ReadAllBytes(path));
        }
        catch (JsonException)
        {
            throw new ThemeStorageCorruptException();
        }

        if (document is not { SchemaVersion: SchemaVersion, Values: { } values } || values.Keys.Any(key => !IsSafeKey(key)) || values.Values.Any(value => value is null))
        {
            throw new ThemeStorageCorruptException();
        }

        return new Dictionary<string, string>(values, StringComparer.Ordinal);
    }

    private sealed class ThemeStorageCorruptException : Exception
    {
    }

    private sealed class StorageDocument
    {
        [JsonPropertyName("schemaVersion")]
        public int SchemaVersion { get; set; }

        [JsonPropertyName("values")]
        public Dictionary<string, string>? Values { get; set; }
    }
}
