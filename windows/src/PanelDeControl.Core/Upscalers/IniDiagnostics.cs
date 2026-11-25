using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What Panel left in OptiScaler.ini when it last wrote it, as the Linux backend's <c>ini_written</c> keeps it.</summary>
public sealed class IniWritten
{
    public IniWritten(double at, IReadOnlyList<KeyValuePair<string, string>> values)
    {
        At = at;
        Values = values;
    }

    /// <summary>Unix seconds.</summary>
    public double At { get; }

    public IReadOnlyList<KeyValuePair<string, string>> Values { get; }
}

public sealed class IniChange
{
    public IniChange(string key, string panel, string? now)
    {
        Key = key;
        Panel = panel;
        Now = now;
    }

    public string Key { get; }

    public string Panel { get; }

    public string? Now { get; }
}

/// <summary>Keys changed in OptiScaler.ini since Panel wrote it; who changed them is not Panel's to know.</summary>
public sealed class IniDrift
{
    public const string Unrecorded = "unrecorded";
    public const string Missing = "missing";
    public const string Changed = "changed";
    public const string AsWritten = "as_written";

    public IniDrift(string status, double? writtenAt, double? modifiedAt, IReadOnlyList<IniChange> keys)
    {
        Status = status;
        WrittenAt = writtenAt;
        ModifiedAt = modifiedAt;
        Keys = keys;
    }

    public string Status { get; }

    public double? WrittenAt { get; }

    public double? ModifiedAt { get; }

    public IReadOnlyList<IniChange> Keys { get; }
}

/// <summary>The OptiScaler.ini facts a support report carries, with the keys and limits of <c>py_modules/upscalers/diagnostics.py</c>.</summary>
public static class IniDiagnostics
{
    public const int ValueLimit = 160;
    public const int MaximumDriftKeys = 24;
    public const int MaximumAdvanced = 40;

    private static readonly string[] QualityModes = { "DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance" };

    public static readonly IReadOnlyList<string> Keys = new[]
    {
        "Upscalers.Dx11Upscaler", "Upscalers.Dx12Upscaler", "Upscalers.VulkanUpscaler",
        "FSR.Fsr4GpuSupport", "FSR.Fsr4Model", "FSR.Fsr4Update", "FSR.Fsr4ForceEnableInt8", "FSR.Fsr4ForceModel", "FSR.UpscalerIndex",
        "FrameGen.Enabled", "FrameGen.FGInput", "FrameGen.FGOutput", "FrameGen.FGNvngxReplacement", "FrameGen.DisableHudless", "OptiFG.HUDFix",
    }
    .Concat(QualityModes.Select(mode => "QualityOverrides.QualityRatio" + mode))
    .Concat(new[]
    {
        "QualityOverrides.QualityRatioOverrideEnabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness", "CAS.Enabled",
        "CAS.MotionSharpnessEnabled", "HelixSR.Int8", "Plugins.LoadAsiPlugins", "Plugins.LoadCustomAmdxc64OnRdna2", "Spoofing.Dxgi", "Log.LogLevel",
    })
    .ToArray();

    private static readonly Regex Scalar = new(@"^(?:auto|true|false|[-+]?[0-9]+(?:\.[0-9]+)?)\z", RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex Choice = new(@"^[A-Za-z][A-Za-z0-9_.-]{0,39}\z", RegexOptions.CultureInvariant);

    public const long MaximumBytes = 1024 * 1024;

    /// <summary>OptiScaler.ini beside the install as plain text; null when it is missing, a link or too large to be one.</summary>
    public static string? ReadText(string target)
    {
        try
        {
            var info = new FileInfo(Path.Combine(target, GameFiles.IniName));
            return info.Exists && (info.Attributes & FileAttributes.ReparsePoint) == 0 && info.Length <= MaximumBytes
                ? System.Text.Encoding.UTF8.GetString(File.ReadAllBytes(info.FullName))
                : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return null;
        }
    }

    public static double? ModifiedAt(string target)
    {
        try
        {
            var info = new FileInfo(Path.Combine(target, GameFiles.IniName));
            return info.Exists ? new DateTimeOffset(info.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0 : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return null;
        }
    }

    /// <summary>Panel's reported keys plus the user's own edited ones, as they stand in the file; null when there is no file to read.</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> Values(string? text, IEnumerable<string>? extra = null)
    {
        if (text is null)
        {
            return Array.Empty<KeyValuePair<string, string>>();
        }

        var wanted = new HashSet<string>(Keys, StringComparer.Ordinal);
        foreach (var key in extra ?? Enumerable.Empty<string>())
        {
            wanted.Add(key);
        }

        var values = new List<KeyValuePair<string, string>>();
        var seen = new Dictionary<string, int>(StringComparer.Ordinal);
        var section = "";
        foreach (var raw in text.Split('\n'))
        {
            var line = raw.Trim();
            if (line.StartsWith("[", StringComparison.Ordinal) && line.EndsWith("]", StringComparison.Ordinal))
            {
                section = line.Substring(1, line.Length - 2);
            }
            else if (line.IndexOf('=') is var equals and > 0 && !line.StartsWith(";", StringComparison.Ordinal))
            {
                var dotted = section + "." + line.Substring(0, equals).Trim();
                if (!wanted.Contains(dotted))
                {
                    continue;
                }

                var value = line.Substring(equals + 1).Trim();
                if (value.Length > ValueLimit)
                {
                    value = value.Substring(0, ValueLimit);
                }

                var pair = new KeyValuePair<string, string>(dotted, value);
                if (seen.TryGetValue(dotted, out var at))
                {
                    values[at] = pair;
                }
                else
                {
                    seen[dotted] = values.Count;
                    values.Add(pair);
                }
            }
        }

        return values;
    }

    /// <summary>What Panel just left in the file, or null when it is not there.</summary>
    public static IniWritten? Written(string? text, IReadOnlyList<KeyValuePair<string, string>> edited, double now) =>
        text is null ? null : new IniWritten(now, Values(text, edited.Select(pair => pair.Key)));

    public static IniDrift Drift(InstalledUpscaler install, string? text, double? modifiedAt)
    {
        var written = install.IniWritten;
        if (written is null)
        {
            return new IniDrift(IniDrift.Unrecorded, null, null, Array.Empty<IniChange>());
        }

        if (text is null)
        {
            return new IniDrift(IniDrift.Missing, written.At, null, Array.Empty<IniChange>());
        }

        var now = Values(text, install.Edited.Select(pair => pair.Key)).ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);
        var changed = written.Values
            .Where(pair => !now.TryGetValue(pair.Key, out var current) || current != pair.Value)
            .Select(pair => new IniChange(pair.Key, pair.Value, now.TryGetValue(pair.Key, out var current) ? current : null))
            .ToList();
        return new IniDrift(changed.Count > 0 ? IniDrift.Changed : IniDrift.AsWritten, written.At, modifiedAt, changed.Take(MaximumDriftKeys).ToList());
    }

    /// <summary>A hand edit as a report may show it: the value only when it is a number, a switch or one of the key's own choices.</summary>
    public static KeyValuePair<string, string?> Request(string? text, string key, string value)
    {
        var omitted = new KeyValuePair<string, string?>(Truncate(key, 120), null);
        if (text is null)
        {
            return omitted;
        }

        var matches = IniText.Schema(text)
            .SelectMany(section => section.Keys.Select(item => (Dotted: section.Name + "." + item.Key, Item: item)))
            .Where(match => key == match.Item.Key || key == match.Dotted)
            .ToList();
        if (matches.Count != 1)
        {
            return omitted;
        }

        var (dotted, entry) = matches[0];
        value = value.Trim();
        if (Scalar.IsMatch(value) || (entry.Choices?.Contains(value) == true && Choice.IsMatch(value)))
        {
            return new KeyValuePair<string, string?>(Truncate(dotted, 120), Truncate(value, 80));
        }

        return omitted;
    }

    private static string Truncate(string value, int limit) => value.Length > limit ? value.Substring(0, limit) : value;
}
