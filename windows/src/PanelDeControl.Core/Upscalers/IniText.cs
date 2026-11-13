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

    /// <summary>Python's <c>str.splitlines(keepends=True)</c> for the breaks an INI can hold.</summary>
    private static List<string> SplitKeepingEnds(string text)
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
