using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

/// <summary>
/// Rewrites Steam class names in theme CSS to the names the running client actually uses.
/// The community table lists every known name of a class across Steam builds; CSS Loader always
/// picks the newest, which breaks when the table is ahead of the installed client. Here the
/// member present in the live client wins and the newest is only a fallback.
/// </summary>
public sealed class ClassTranslator
{
    private static readonly Regex ClassSelector = new(@"\.([_a-zA-Z]+[_a-zA-Z0-9-]*)", RegexOptions.CultureInvariant | RegexOptions.Compiled);
    private static readonly Regex ClassAttribute = new(@"\[class([*^|~]?)=""([_a-zA-Z0-9-]*)""\]", RegexOptions.CultureInvariant | RegexOptions.Compiled);

    private readonly IReadOnlyDictionary<string, string> translations;

    private ClassTranslator(IReadOnlyDictionary<string, string> translations, string fingerprint)
    {
        this.translations = translations;
        Fingerprint = fingerprint;
    }

    public static ClassTranslator Identity { get; } = new(new Dictionary<string, string>(), "identity");

    public string Fingerprint { get; }

    public int Count => translations.Count;

    public static IReadOnlyList<IReadOnlyList<string>> ParseTable(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new FormatException("Class table must be an object");
        }

        var groups = new List<IReadOnlyList<string>>();
        foreach (var entry in document.RootElement.EnumerateObject())
        {
            if (entry.Value.ValueKind != JsonValueKind.Array)
            {
                continue;
            }

            var names = entry.Value.EnumerateArray()
                .Where(value => value.ValueKind == JsonValueKind.String)
                .Select(value => value.GetString()!)
                .Where(name => name.Length > 0)
                .ToArray();
            if (names.Length > 1)
            {
                groups.Add(names);
            }
        }

        return groups;
    }

    public static ClassTranslator Create(
        IReadOnlyList<IReadOnlyList<string>> table,
        IReadOnlySet<string>? liveClasses)
    {
        var translations = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var names in table)
        {
            var target = liveClasses is { Count: > 0 }
                ? names.LastOrDefault(liveClasses.Contains) ?? names[^1]
                : names[^1];
            foreach (var name in names)
            {
                if (name != target && (liveClasses is null || !liveClasses.Contains(name)))
                {
                    translations[name] = target;
                }
            }
        }

        var canonical = new StringBuilder();
        foreach (var pair in translations.OrderBy(pair => pair.Key, StringComparer.Ordinal))
        {
            canonical.Append(pair.Key).Append('=').Append(pair.Value).Append('\n');
        }

        var fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical.ToString())))[..16];
        return new ClassTranslator(translations, fingerprint);
    }

    public string Translate(string css)
    {
        if (translations.Count == 0)
        {
            return css;
        }

        var selectors = ClassSelector.Replace(css, match =>
            translations.TryGetValue(match.Groups[1].Value, out var live) ? "." + live : match.Value);
        return ClassAttribute.Replace(selectors, match =>
            translations.TryGetValue(match.Groups[2].Value, out var live)
                ? $"[class{match.Groups[1].Value}=\"{live}\"]"
                : match.Value);
    }
}
