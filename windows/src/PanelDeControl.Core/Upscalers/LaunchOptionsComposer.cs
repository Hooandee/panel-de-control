using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

public sealed class LaunchOptionsPlan
{
    public LaunchOptionsPlan(string value, IReadOnlyList<string> added)
    {
        Value = value;
        Added = added;
    }

    public string Value { get; }

    public IReadOnlyList<string> Added { get; }
}

/// <summary>
/// Port of the args-only subset of src/launch/compose.ts and src/upscalers/model.ts. A string beyond the
/// simple env/wrapper/%command%/args model is never rewritten: every operation returns null for it.
/// </summary>
public static class LaunchOptionsComposer
{
    private const string Command = "%command%";

    private static readonly char[] ShellOperators = { ';', '&', '|', '`', '<', '>', '$' };
    private static readonly Regex EnvAssignmentPattern = new("^[A-Za-z_][A-Za-z0-9_]*=", RegexOptions.CultureInvariant);
    private static readonly Regex ForeignGameIdPattern = new(
        "^(?:epic|gog|amazon|ubisoft|battlenet|microsoft|gamevault|itch):[A-Za-z0-9][A-Za-z0-9._-]*$",
        RegexOptions.CultureInvariant);
    private static readonly Regex WineOverridesPattern = new(
        @"^WINEDLLOVERRIDES=([""'])[a-zA-Z0-9_.*=,;\s-]*\1$",
        RegexOptions.CultureInvariant);

    public static LaunchOptionsPlan? Apply(string launch, IReadOnlyList<string> args)
    {
        var parsed = Parse(launch);
        if (parsed is null)
        {
            return null;
        }

        var added = args.Where(arg => !parsed.Suffix.Contains(arg, StringComparer.Ordinal)).ToList();
        parsed.Suffix.AddRange(added);
        return new LaunchOptionsPlan(Serialize(parsed), added);
    }

    public static string? Revert(string launch, IReadOnlyList<string> added)
    {
        var parsed = Parse(launch);
        if (parsed is null)
        {
            return null;
        }

        parsed.Suffix.RemoveAll(token => added.Contains(token, StringComparer.Ordinal));
        return Serialize(parsed);
    }

    /// <summary>Takes out what a previous install added, then adds the new args; <c>Added</c> lists only the args that were not already there.</summary>
    public static LaunchOptionsPlan? Replace(string launch, IReadOnlyList<string> previouslyAdded, IReadOnlyList<string> args)
    {
        var reverted = Revert(launch, previouslyAdded);
        return reverted is null ? null : Apply(reverted, args);
    }

    private static Parsed? Parse(string? raw)
    {
        raw ??= string.Empty;
        var (tokens, unbalanced) = Tokenize(raw);
        var commandCount = tokens.Count(token => token == Command);
        var rawCommandCount = raw.Split(new[] { Command }, StringSplitOptions.None).Length - 1;
        if (unbalanced
            || raw.Contains('\r') || raw.Contains('\n')
            || tokens.Any(HasShellOperators)
            || commandCount > 1
            || rawCommandCount != commandCount)
        {
            return null;
        }

        var index = tokens.IndexOf(Command);
        var prefix = index < 0 ? new List<string>() : tokens.GetRange(0, index);
        var suffix = tokens.GetRange(index + 1, tokens.Count - index - 1);
        var envs = new List<string>();
        var wrappers = new List<string>();
        foreach (var token in prefix)
        {
            (EnvAssignmentPattern.IsMatch(token) ? envs : wrappers).Add(token);
        }

        var id = suffix.FindIndex(token => ForeignGameIdPattern.IsMatch(token));
        if (id < 0)
        {
            return new Parsed(envs, wrappers, suffix, index >= 0, null);
        }

        var after = suffix.GetRange(id + 1, suffix.Count - id - 1);
        envs.AddRange(after.Where(token => EnvAssignmentPattern.IsMatch(token)));
        var kept = suffix.GetRange(0, id + 1);
        kept.AddRange(after.Where(token => !EnvAssignmentPattern.IsMatch(token)));
        return new Parsed(envs, wrappers, kept, index >= 0, suffix[id]);
    }

    private static string Serialize(Parsed parsed)
    {
        if (parsed.Envs.Count == 0 && parsed.Wrappers.Count == 0 && parsed.Suffix.Count == 0)
        {
            return string.Empty;
        }

        var parts = new List<string>();
        if (parsed.EnvAfter is not null && parsed.Suffix.Contains(parsed.EnvAfter, StringComparer.Ordinal))
        {
            var at = parsed.Suffix.IndexOf(parsed.EnvAfter);
            if (parsed.Wrappers.Count > 0)
            {
                parts.AddRange(parsed.Wrappers);
                parts.Add(Command);
            }

            parts.AddRange(parsed.Suffix.Take(at + 1));
            parts.AddRange(parsed.Envs);
            parts.AddRange(parsed.Suffix.Skip(at + 1));
            return string.Join(" ", parts);
        }

        parts.AddRange(parsed.Envs);
        parts.AddRange(parsed.Wrappers);
        if (parsed.HasCommand || parsed.Envs.Count > 0 || parsed.Wrappers.Count > 0)
        {
            parts.Add(Command);
        }

        parts.AddRange(parsed.Suffix);
        return string.Join(" ", parts);
    }

    private static (List<string> Tokens, bool Unbalanced) Tokenize(string text)
    {
        var tokens = new List<string>();
        var current = new StringBuilder();
        char? quote = null;
        var escaped = false;
        foreach (var ch in text.Trim())
        {
            if (escaped)
            {
                current.Append(ch);
                escaped = false;
            }
            else if (ch == '\\')
            {
                current.Append(ch);
                escaped = true;
            }
            else if (quote is not null)
            {
                current.Append(ch);
                if (ch == quote)
                {
                    quote = null;
                }
            }
            else if (ch is '"' or '\'')
            {
                current.Append(ch);
                quote = ch;
            }
            else if (char.IsWhiteSpace(ch))
            {
                if (current.Length > 0)
                {
                    tokens.Add(current.ToString());
                    current.Clear();
                }
            }
            else
            {
                current.Append(ch);
            }
        }

        if (current.Length > 0)
        {
            tokens.Add(current.ToString());
        }

        return (tokens, quote is not null || escaped);
    }

    private static bool HasShellOperators(string token)
    {
        var candidate = WineOverridesPattern.IsMatch(token) ? token.Replace(";", string.Empty) : token;
        return candidate.IndexOfAny(ShellOperators) >= 0;
    }

    private sealed class Parsed
    {
        public Parsed(List<string> envs, List<string> wrappers, List<string> suffix, bool hasCommand, string? envAfter)
        {
            Envs = envs;
            Wrappers = wrappers;
            Suffix = suffix;
            HasCommand = hasCommand;
            EnvAfter = envAfter;
        }

        public List<string> Envs { get; }

        public List<string> Wrappers { get; }

        public List<string> Suffix { get; }

        public bool HasCommand { get; }

        public string? EnvAfter { get; }
    }
}
