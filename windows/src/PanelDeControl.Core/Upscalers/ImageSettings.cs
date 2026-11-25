using System.Globalization;
using System.Numerics;

namespace PanelDeControl.Core.Upscalers;

public sealed class ImageSettingsException : Exception
{
    public ImageSettingsException(string code)
        : base(code)
    {
        Code = code;
    }

    public string Code { get; }
}

/// <summary>Sharpness as the image controls show it: on/off (null when the INI says neither) and 0–1 (null for <c>auto</c>).</summary>
public sealed class ImageSharpness
{
    public bool? Enabled { get; set; }

    public double? Value { get; set; }
}

public sealed class ImageSettingsState
{
    public bool Supported { get; set; }

    public ImageSharpness? Sharpness { get; set; }

    /// <summary>HelixSR's INT8 switch (<c>auto</c>, <c>on</c>, <c>off</c>), only for another tool's HLX DLSS.</summary>
    public string? Int8 { get; set; }

    /// <summary>Panel changed these keys and can put them back.</summary>
    public bool Managed { get; set; }

    public string? Reason { get; set; }
}

/// <summary>What the user asked to change; a field left null is left alone.</summary>
public sealed class ImageSettingsRequest
{
    public ImageSharpness? Sharpness { get; set; }

    public string? Int8 { get; set; }
}

/// <summary>The originals of the keys Panel changed and what it wrote, so a restore only undoes its own values (<c>image_settings</c> in state).</summary>
public sealed class ImageSettingsReceipt
{
    public string Target { get; set; } = "";

    public List<KeyValuePair<string, string>> Original { get; set; } = new();

    public List<KeyValuePair<string, string>> Applied { get; set; } = new();

    public ImageSettingsReceipt Copy() => new() { Target = Target, Original = Original.ToList(), Applied = Applied.ToList() };
}

/// <summary>Bounded, reversible image controls for recognized OptiScaler INI layouts (<c>image_settings.py</c>).</summary>
public static class ImageSettings
{
    public const int MaximumBytes = 256 * 1024;

    public static readonly IReadOnlyList<string> SharpnessKeys = new[] { "CAS.Enabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness" };

    public static readonly IReadOnlyList<string> ManagedSharpnessKeys = new[] { "CAS.Enabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness", "CAS.MotionSharpnessEnabled" };

    public static readonly IReadOnlyList<string> Keys = new[] { "CAS.Enabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness", "CAS.MotionSharpnessEnabled", "HelixSR.Int8" };

    private static readonly string[] Tristate = { "true", "false", "auto" };
    private static readonly string[] Int8Modes = { "auto", "on", "off" };

    /// <summary>The image keys as Python's strict <c>configparser</c> reads them; any malformed or repeated entry is <c>invalid_config</c>.</summary>
    public static IReadOnlyDictionary<string, string> Values(string text)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var sections = new HashSet<string>(StringComparer.Ordinal);
        string? section = null;
        string? pendingKey = null;
        var pendingValue = new List<string>();
        var pendingIndent = 0;
        void Flush()
        {
            if (pendingKey is not null && section is not null)
            {
                var dotted = section + "." + pendingKey;
                if (!seen.Add(dotted.ToLowerInvariant()))
                {
                    throw new ImageSettingsException("invalid_config");
                }
                if (Keys.Contains(dotted))
                {
                    result[dotted] = string.Join("\n", pendingValue).Trim();
                }
            }
            pendingKey = null;
            pendingValue.Clear();
        }

        var options = new HashSet<string>(StringComparer.Ordinal);
        foreach (var raw in IniText.SplitKeepingEnds(text))
        {
            var line = raw.TrimEnd('\r', '\n');
            var stripped = line.Trim();
            if (stripped.Length == 0 || stripped[0] == '#' || stripped[0] == ';')
            {
                // configparser keeps a blank line inside a multi-line value only to strip it at the end.
                if (stripped.Length == 0 && pendingKey is not null)
                {
                    pendingValue.Add("");
                }
                continue;
            }
            var indent = line.Length - line.TrimStart().Length;
            if (pendingKey is not null && indent > pendingIndent)
            {
                pendingValue.Add(stripped);
                continue;
            }
            Flush();
            if (stripped.StartsWith("[", StringComparison.Ordinal) && stripped.LastIndexOf(']') is var close && close > 1)
            {
                var name = stripped.Substring(1, close - 1);
                if (!sections.Add(name))
                {
                    throw new ImageSettingsException("invalid_config");
                }
                section = name;
                options.Clear();
                continue;
            }
            if (section is null)
            {
                throw new ImageSettingsException("invalid_config");
            }
            var equals = stripped.IndexOf('=');
            var colon = stripped.IndexOf(':');
            var at = equals < 0 ? colon : colon < 0 ? equals : Math.Min(equals, colon);
            if (at < 0)
            {
                throw new ImageSettingsException("invalid_config");
            }
            var key = stripped.Substring(0, at).TrimEnd();
            if (key.Length == 0 || !options.Add(key))
            {
                throw new ImageSettingsException("invalid_config");
            }
            pendingKey = key;
            pendingIndent = indent;
            pendingValue.Add(stripped.Substring(at + 1).Trim());
        }
        Flush();
        return result;
    }

    public static ImageSettingsState State(string text, bool helix, bool managed)
    {
        var settings = Values(text);
        ImageSharpness? sharpness = null;
        if (SharpnessKeys.All(settings.ContainsKey))
        {
            var enabled = settings[SharpnessKeys[0]];
            var overridden = settings[SharpnessKeys[1]];
            if (!Tristate.Contains(enabled) || !Tristate.Contains(overridden))
            {
                throw new ImageSettingsException("invalid_config");
            }
            var raw = settings[SharpnessKeys[2]];
            double? number = null;
            if (raw != "auto")
            {
                if (!PythonFloat(raw, out var parsed) || double.IsNaN(parsed) || double.IsInfinity(parsed) || parsed < 0 || parsed > 1)
                {
                    throw new ImageSettingsException("invalid_config");
                }
                number = parsed;
            }
            var motion = settings.TryGetValue("CAS.MotionSharpnessEnabled", out var value) ? value : "auto";
            if (!Tristate.Contains(motion))
            {
                throw new ImageSettingsException("invalid_config");
            }
            bool? active = null;
            if (overridden == "true" && number is not null)
            {
                if (number == 0 && motion != "true")
                {
                    active = false;
                }
                else if (number > 0 && enabled == "true")
                {
                    active = true;
                }
            }
            sharpness = new ImageSharpness { Enabled = active, Value = number };
        }
        string? int8 = helix && settings.TryGetValue("HelixSR.Int8", out var mode) ? mode : null;
        if (int8 is not null && !Int8Modes.Contains(int8))
        {
            throw new ImageSettingsException("invalid_config");
        }
        var supported = sharpness is not null || int8 is not null;
        return new ImageSettingsState
        {
            Supported = supported,
            Sharpness = sharpness,
            Int8 = int8,
            Managed = managed,
            Reason = supported ? null : "unsupported_layout",
        };
    }

    public static IReadOnlyList<KeyValuePair<string, string>> Changes(ImageSettingsRequest request, ImageSettingsState current, string text)
    {
        if (request.Sharpness is null && request.Int8 is null)
        {
            throw new ImageSettingsException("image_settings_value");
        }
        var result = new List<KeyValuePair<string, string>>();
        if (request.Sharpness is { } wanted)
        {
            if (current.Sharpness is null || wanted.Enabled is not { } enabled || wanted.Value is not { } number
                || double.IsNaN(number) || double.IsInfinity(number) || number < 0 || number > 1)
            {
                throw new ImageSettingsException("image_settings_value");
            }
            result.Add(Pair("CAS.Enabled", enabled ? "true" : "false"));
            result.Add(Pair("Sharpness.OverrideSharpness", "true"));
            result.Add(Pair("Sharpness.Sharpness", enabled ? Fixed2(number) : "0.00"));
            if (!enabled && Values(text).ContainsKey("CAS.MotionSharpnessEnabled"))
            {
                result.Add(Pair("CAS.MotionSharpnessEnabled", "false"));
            }
        }
        if (request.Int8 is not null)
        {
            if (current.Int8 is null || !Int8Modes.Contains(request.Int8))
            {
                throw new ImageSettingsException("image_settings_value");
            }
            result.Add(Pair("HelixSR.Int8", request.Int8));
        }
        return result;
    }

    /// <summary>The receipt after writing <paramref name="changes"/>: a key's original is only taken when Panel's last value is gone.</summary>
    public static ImageSettingsReceipt Receipt(ImageSettingsReceipt? previous, string target, string text, IReadOnlyList<KeyValuePair<string, string>> changes)
    {
        var receipt = previous is not null && previous.Target == target ? previous.Copy() : new ImageSettingsReceipt { Target = target };
        var current = Values(text);
        foreach (var change in changes)
        {
            var applied = Find(receipt.Applied, change.Key);
            if (Find(receipt.Original, change.Key) is null || (current.TryGetValue(change.Key, out var now) ? now : null) != applied)
            {
                Set(receipt.Original, change.Key, current[change.Key]);
            }
            Set(receipt.Applied, change.Key, change.Value);
        }
        return receipt;
    }

    /// <summary>The text with each original back, only where the key still holds what Panel wrote.</summary>
    public static string Restored(string text, ImageSettingsReceipt receipt)
    {
        var current = Values(text);
        var changes = receipt.Original
            .Where(pair => Keys.Contains(pair.Key) && current.TryGetValue(pair.Key, out var now) && now == Find(receipt.Applied, pair.Key))
            .ToList();
        return IniText.Apply(text, changes);
    }

    /// <summary>Python's <c>f"{number:.2f}"</c>: the exact binary value, ties to even.</summary>
    public static string Fixed2(double number)
    {
        var bits = BitConverter.DoubleToInt64Bits(number);
        var negative = bits < 0;
        var exponent = (int)((bits >> 52) & 0x7FF);
        var mantissa = bits & 0xFFFFFFFFFFFFFL;
        if (exponent == 0)
        {
            exponent = 1;
        }
        else
        {
            mantissa |= 1L << 52;
        }
        exponent -= 1075;
        // number = mantissa * 2^exponent; scaled = number * 100 as numerator / denominator.
        BigInteger numerator = new BigInteger(mantissa) * 100;
        BigInteger denominator = BigInteger.One;
        if (exponent >= 0)
        {
            numerator <<= exponent;
        }
        else
        {
            denominator <<= -exponent;
        }
        var whole = BigInteger.DivRem(numerator, denominator, out var remainder);
        var twice = remainder * 2;
        if (twice > denominator || (twice == denominator && !whole.IsEven))
        {
            whole += 1;
        }
        var digits = whole.ToString(CultureInfo.InvariantCulture).PadLeft(3, '0');
        var text = digits.Substring(0, digits.Length - 2) + "." + digits.Substring(digits.Length - 2);
        return negative && whole != 0 ? "-" + text : text;
    }

    internal static string? Find(IReadOnlyList<KeyValuePair<string, string>> pairs, string key)
    {
        foreach (var pair in pairs)
        {
            if (pair.Key == key)
            {
                return pair.Value;
            }
        }
        return null;
    }

    private static void Set(List<KeyValuePair<string, string>> pairs, string key, string value)
    {
        var index = pairs.FindIndex(pair => pair.Key == key);
        if (index >= 0)
        {
            pairs[index] = Pair(key, value);
        }
        else
        {
            pairs.Add(Pair(key, value));
        }
    }

    private static KeyValuePair<string, string> Pair(string key, string value) => new(key, value);

    /// <summary>Python's <c>float()</c> for what an INI can hold: decimal or exponent, no thousands separators.</summary>
    private static bool PythonFloat(string text, out double value) =>
        double.TryParse(text.Replace("_", ""), NumberStyles.Float, CultureInfo.InvariantCulture, out value)
        && !text.StartsWith("_", StringComparison.Ordinal) && !text.EndsWith("_", StringComparison.Ordinal);
}
