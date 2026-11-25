using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

/// <summary>In-place OptiScaler.ini edits that keep comments, order and line endings.</summary>
public static class IniText
{
    private static readonly Regex Section = new(@"^\s*\[(?<name>[^\]]+)\]\s*$", RegexOptions.CultureInvariant);

    /// <summary>Set <c>Section.Key=value</c> pairs, appending keys or sections that are missing.</summary>
    public static string Apply(string text, IEnumerable<KeyValuePair<string, string>> overrides)
    {
        var newline = text.Contains("\r\n") ? "\r\n" : "\n";
        var lines = SplitKeepingEnds(text);
        foreach (var pair in overrides)
        {
            var dot = pair.Key.IndexOf('.');
            var section = pair.Key.Substring(0, dot);
            var key = pair.Key.Substring(dot + 1);
            var keyPattern = new Regex(@"^\s*" + Regex.Escape(key) + @"\s*=", RegexOptions.CultureInvariant);
            var inside = false;
            int? insertAt = null;
            var replaced = false;
            for (var index = 0; index < lines.Count; index++)
            {
                var match = Section.Match(TrimEnd(lines[index]));
                if (match.Success)
                {
                    if (inside)
                    {
                        insertAt = index;
                        break;
                    }
                    inside = match.Groups["name"].Value == section;
                    continue;
                }
                if (inside && keyPattern.IsMatch(lines[index]))
                {
                    var ending = lines[index].Substring(TrimEnd(lines[index]).Length);
                    lines[index] = key + "=" + pair.Value + (ending.Length == 0 ? newline : ending);
                    replaced = true;
                    break;
                }
            }
            if (replaced)
            {
                continue;
            }
            if (insertAt is null)
            {
                if (inside)
                {
                    insertAt = lines.Count;
                }
                else
                {
                    if (lines.Count > 0 && !EndsWithBreak(lines[lines.Count - 1]))
                    {
                        lines[lines.Count - 1] += newline;
                    }
                    lines.Add("[" + section + "]" + newline);
                    insertAt = lines.Count;
                }
            }
            var at = insertAt.Value;
            if (lines.Count > 0 && at > 0 && !EndsWithBreak(lines[at - 1]))
            {
                lines[at - 1] += newline;
            }
            lines.Insert(at, key + "=" + pair.Value + newline);
        }
        return string.Concat(lines);
    }

    public static string? Read(string text, string dotted)
    {
        var dot = dotted.IndexOf('.');
        var section = dotted.Substring(0, dot);
        var key = dotted.Substring(dot + 1);
        var inside = false;
        foreach (var raw in SplitKeepingEnds(text))
        {
            var line = TrimEnd(raw);
            var match = Section.Match(line);
            if (match.Success)
            {
                inside = match.Groups["name"].Value == section;
                continue;
            }
            if (!inside)
            {
                continue;
            }
            var separator = line.IndexOf('=');
            if (separator >= 0 && line.Substring(0, separator).Trim() == key)
            {
                return line.Substring(separator + 1).Trim();
            }
        }
        return null;
    }

    private static readonly Regex Default = new(@"Default \(auto\) is ([^\s,;]+)|Default is ([^\s,;]+)", RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
    private static readonly Regex ChoiceToken = new(@"^[A-Za-z0-9_.\-]+$", RegexOptions.CultureInvariant);
    private static readonly Regex Parenthesised = new(@"\([^)]*\)", RegexOptions.CultureInvariant);

    /// <summary>Every section and key with the help OptiScaler writes above it, its allowed values and default (<c>ini.schema</c>).</summary>
    public static IReadOnlyList<IniSchemaSection> Schema(string text, ISet<string>? managed = null)
    {
        var sections = new List<IniSchemaSection>();
        var help = new List<string>();
        foreach (var raw in SplitKeepingEnds(text))
        {
            var line = TrimEnd(raw);
            var stripped = PythonStrip(line);
            var match = Section.Match(line);
            if (match.Success)
            {
                sections.Add(new IniSchemaSection(match.Groups["name"].Value));
                help = new List<string>();
            }
            else if (stripped.StartsWith(";", StringComparison.Ordinal))
            {
                var body = PythonStrip(stripped.TrimStart(';'));
                if (body.Length > 0 && body.Any(character => character != '-'))
                {
                    help.Add(body.Length > 300 ? body.Substring(0, 300) : body);
                }
            }
            else if (stripped.Contains("=") && sections.Count > 0)
            {
                var separator = stripped.IndexOf('=');
                var key = PythonStrip(stripped.Substring(0, separator));
                var value = PythonStrip(stripped.Substring(separator + 1));
                var section = sections[sections.Count - 1];
                var dotted = section.Name + "." + key;
                string? fallback = null;
                foreach (var item in help)
                {
                    var found = Default.Match(item);
                    if (found.Success)
                    {
                        fallback = found.Groups[1].Success ? found.Groups[1].Value : found.Groups[2].Value;
                        break;
                    }
                }
                var choices = Choices(help);
                if (choices is not null && value.Length > 0 && !choices.Contains(value))
                {
                    choices.Add(value);
                }
                section.Keys.Add(new IniSchemaKey(key, value, help.Take(12).ToList(), choices, fallback, managed?.Contains(dotted) == true));
                help = new List<string>();
            }
            else if (stripped.Length == 0)
            {
                help = new List<string>();
            }
        }
        return sections.Where(section => section.Keys.Count > 0).ToList();
    }

    /// <summary>Allowed values from OptiScaler's own comment: <c>a, b, c - Default (auto) is a</c> or <c>true or false</c>.</summary>
    private static List<string>? Choices(IReadOnlyList<string> help)
    {
        for (var index = help.Count - 1; index >= 0; index--)
        {
            var line = help[index];
            var at = line.IndexOf(" - Default", StringComparison.Ordinal);
            if (at < 0)
            {
                continue;
            }
            var listed = line.Substring(0, at);
            if (PythonStrip(listed).ToLowerInvariant() == "true or false")
            {
                return new List<string> { "auto", "true", "false" };
            }
            listed = Parenthesised.Replace(listed, "");
            var tokens = listed.Split(',').Select(part => PythonStrip(part).Split(' ')[0]).ToList();
            if (tokens.Count > 1 && tokens.All(token => ChoiceToken.IsMatch(token)) && !tokens.Any(token => char.IsDigit(token[0])))
            {
                var result = new List<string> { "auto" };
                result.AddRange(tokens.Where(token => token != "auto"));
                return result;
            }
        }
        return null;
    }

    /// <summary>Python's argument-less <c>str.strip()</c>: every whitespace character, not only spaces.</summary>
    internal static string PythonStrip(string value) => value.Trim();

    /// <summary>Python's <c>str.splitlines(keepends=True)</c> for the breaks an INI can hold.</summary>
    internal static List<string> SplitKeepingEnds(string text)
    {
        var lines = new List<string>();
        var start = 0;
        for (var index = 0; index < text.Length; index++)
        {
            var character = text[index];
            if (character != '\n' && character != '\r')
            {
                continue;
            }
            if (character == '\r' && index + 1 < text.Length && text[index + 1] == '\n')
            {
                index++;
            }
            lines.Add(text.Substring(start, index + 1 - start));
            start = index + 1;
        }
        if (start < text.Length)
        {
            lines.Add(text.Substring(start));
        }
        return lines;
    }

    private static string TrimEnd(string line) => line.TrimEnd('\r', '\n');

    private static bool EndsWithBreak(string line) => line.EndsWith("\n", StringComparison.Ordinal) || line.EndsWith("\r", StringComparison.Ordinal);
}

public sealed class IniSchemaSection
{
    public IniSchemaSection(string name)
    {
        Name = name;
    }

    public string Name { get; }

    public List<IniSchemaKey> Keys { get; } = new();
}

public sealed class IniSchemaKey
{
    public IniSchemaKey(string key, string value, IReadOnlyList<string> help, IReadOnlyList<string>? choices, string? fallback, bool managed)
    {
        Key = key;
        Value = value;
        Help = help;
        Choices = choices;
        Default = fallback;
        Managed = managed;
    }

    public string Key { get; }

    public string Value { get; }

    public IReadOnlyList<string> Help { get; }

    /// <summary>Null when OptiScaler's comment lists no closed set of values.</summary>
    public IReadOnlyList<string>? Choices { get; }

    public string? Default { get; }

    /// <summary>Panel writes this key itself, so the editor shows it read-only.</summary>
    public bool Managed { get; }
}
