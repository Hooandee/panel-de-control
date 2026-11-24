namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// REFramework's flat <c>key=value</c> config, which Panel seeds so its menu does not open over the game on first launch
/// (handhelds have no Insert key to close it) and, for some recipes, so its TemporalUpscaler follows Panel's quality.
/// Same keys and rules as the Linux backend.
/// </summary>
public static class ReframeworkConfig
{
    public const string FileName = "re2_fw_config.txt";
    public const string Asset = "reframework-nightly";
    public const long MaximumBytes = 1024 * 1024;

    public static readonly IReadOnlyList<KeyValuePair<string, string>> Closed = new[]
    {
        new KeyValuePair<string, string>("REFrameworkConfig_RememberMenuState", "true"),
        new KeyValuePair<string, string>("REFrameworkConfig_MenuOpen", "false"),
    };

    public static readonly IReadOnlyList<string> UpscalerKeys = new[]
    {
        "TemporalUpscaler_Enabled", "TemporalUpscaler_UseNativeResolution", "TemporalUpscaler_UpscaleQuality",
    };

    private static readonly Dictionary<string, string> Quality = new(StringComparer.Ordinal)
    {
        ["performance"] = "0", ["balanced"] = "1", ["quality"] = "2", ["ultra"] = "3",
    };

    /// <summary>Panel's quality as REFramework's TemporalUpscaler settings: native renders at full size (its DLAA mode).</summary>
    public static IReadOnlyList<KeyValuePair<string, string?>> Upscaler(string? quality) => quality == "native"
        ? new[]
        {
            new KeyValuePair<string, string?>("TemporalUpscaler_Enabled", "true"),
            new KeyValuePair<string, string?>("TemporalUpscaler_UseNativeResolution", "true"),
        }
        : new[]
        {
            new KeyValuePair<string, string?>("TemporalUpscaler_Enabled", "true"),
            new KeyValuePair<string, string?>("TemporalUpscaler_UseNativeResolution", "false"),
            new KeyValuePair<string, string?>("TemporalUpscaler_UpscaleQuality", quality is not null && Quality.TryGetValue(quality, out var value) ? value : "1"),
        };

    /// <summary>The config with these keys set (null removes one); every other line kept.</summary>
    public static string WithKeys(string text, IReadOnlyList<KeyValuePair<string, string?>> values)
    {
        var lookup = new Dictionary<string, string?>(StringComparer.Ordinal);
        foreach (var pair in values)
        {
            lookup[pair.Key] = pair.Value;
        }
        var lines = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var line in SplitLines(text))
        {
            var key = line.Contains('=') ? line.Substring(0, line.IndexOf('=')).Trim() : null;
            if (key is not null && lookup.TryGetValue(key, out var value))
            {
                if (seen.Contains(key) || value is null)
                {
                    continue;
                }
                seen.Add(key);
                lines.Add(key + "=" + value);
                continue;
            }
            lines.Add(line);
        }
        foreach (var pair in values)
        {
            if (!seen.Contains(pair.Key) && pair.Value is not null && seen.Add(pair.Key))
            {
                lines.Add(pair.Key + "=" + pair.Value);
            }
        }
        return string.Join("\n", lines) + "\n";
    }

    /// <summary>The values these keys have in a config, null for the ones it lacks.</summary>
    public static IReadOnlyList<KeyValuePair<string, string?>> Keys(string text, IEnumerable<string> names)
    {
        var found = names.Distinct(StringComparer.Ordinal).ToDictionary(name => name, _ => (string?)null, StringComparer.Ordinal);
        foreach (var line in SplitLines(text))
        {
            var index = line.IndexOf('=');
            var key = (index < 0 ? line : line.Substring(0, index)).Trim();
            if (found.ContainsKey(key))
            {
                found[key] = index < 0 ? "" : line.Substring(index + 1).Trim();
            }
        }
        return found.ToList();
    }

    public static IEnumerable<string> AllKeys => Closed.Select(pair => pair.Key).Concat(UpscalerKeys);

    // Python's str.splitlines over the line breaks a text config can hold.
    private static IEnumerable<string> SplitLines(string text)
    {
        var normalized = text.Replace("\r\n", "\n").Replace('\r', '\n');
        if (normalized.EndsWith("\n", StringComparison.Ordinal))
        {
            normalized = normalized.Substring(0, normalized.Length - 1);
        }
        return text.Length == 0 ? Array.Empty<string>() : normalized.Split('\n');
    }
}
