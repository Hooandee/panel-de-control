using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Steam;

/// <summary>Steam's text KeyValues (libraryfolders.vdf, appmanifest_*.acf): keys lower-cased, duplicates refused.</summary>
public static class ValveTextVdf
{
    public const int MaxBytes = 8 * 1024 * 1024;
    public const int MaxDepth = 32;

    // Python's \s also counts the ASCII separators U+001C-U+001F as whitespace.
    private static readonly Regex Token = new(
        @"[\s\x1c-\x1f]+|//[^\n]*|""((?:\\.|[^""\\])*)""|([{}])|([^\s\x1c-\x1f{}""]+)",
        RegexOptions.CultureInvariant);

    private static readonly Regex Escape = new(@"\\([\\""])", RegexOptions.CultureInvariant);

    /// <exception cref="VdfFormatException">The text is not valid KeyValues.</exception>
    public static VdfObject Parse(byte[] data)
    {
        if (data.Length > MaxBytes)
        {
            throw new VdfFormatException(VdfFormatException.Oversized);
        }

        var offset = data.Length >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF ? 3 : 0;
        string text;
        try
        {
            text = new UTF8Encoding(false, true).GetString(data, offset, data.Length - offset);
        }
        catch (DecoderFallbackException)
        {
            throw new VdfFormatException(VdfFormatException.Decode);
        }

        return new Parser(Tokenize(text)).Document();
    }

    /// <summary>The file's KeyValues, or null when it is missing, unreadable or malformed.</summary>
    public static VdfObject? TryRead(IReadOnlyFileSystem fileSystem, string path)
    {
        var data = FileSystemPath.ReadAtMost(fileSystem, path, MaxBytes + 1);
        if (data is null)
        {
            return null;
        }

        try
        {
            return Parse(data);
        }
        catch (VdfFormatException)
        {
            return null;
        }
    }

    private static List<string> Tokenize(string text)
    {
        var tokens = new List<string>();
        var position = 0;
        while (position < text.Length)
        {
            var match = Token.Match(text, position);
            if (!match.Success || match.Index != position)
            {
                throw new VdfFormatException(VdfFormatException.Malformed);
            }

            position = match.Index + match.Length;
            if (match.Groups[1].Success)
            {
                tokens.Add(Escape.Replace(match.Groups[1].Value, "$1"));
            }
            else if (match.Groups[2].Success)
            {
                tokens.Add(match.Groups[2].Value);
            }
            else if (match.Groups[3].Success)
            {
                tokens.Add(match.Groups[3].Value);
            }
        }

        return tokens;
    }

    private sealed class Parser
    {
        private readonly List<string> tokens;
        private int cursor;

        public Parser(List<string> tokens)
        {
            this.tokens = tokens;
        }

        public VdfObject Document() => Object(0, nested: false);

        private VdfObject Object(int depth, bool nested)
        {
            if (depth > MaxDepth)
            {
                throw new VdfFormatException(VdfFormatException.Malformed);
            }

            var result = new VdfObject();
            while (cursor < tokens.Count)
            {
                var key = tokens[cursor++];
                if (key == "}")
                {
                    if (nested)
                    {
                        return result;
                    }

                    throw new VdfFormatException(VdfFormatException.Malformed);
                }

                if (key == "{" || cursor == tokens.Count)
                {
                    throw new VdfFormatException(VdfFormatException.Malformed);
                }

                var token = tokens[cursor++];
                object value = token switch
                {
                    "{" => Object(depth + 1, nested: true),
                    "}" => throw new VdfFormatException(VdfFormatException.Malformed),
                    _ => token,
                };
                if (!result.TryAdd(key.ToLowerInvariant(), value))
                {
                    throw new VdfFormatException(VdfFormatException.DuplicateKey);
                }
            }

            if (nested)
            {
                throw new VdfFormatException(VdfFormatException.Malformed);
            }

            return result;
        }
    }
}

public sealed class VdfFormatException : Exception
{
    public const string Malformed = "malformed_vdf";
    public const string DuplicateKey = "duplicate_vdf_key";
    public const string Oversized = "oversized_vdf";
    public const string Decode = "decode";

    public VdfFormatException(string code)
        : base(code)
    {
        Code = code;
    }

    public string Code { get; }
}

/// <summary>A KeyValues object in file order; each value is a <see cref="string"/> or a nested <see cref="VdfObject"/>.</summary>
public sealed class VdfObject
{
    private readonly List<KeyValuePair<string, object>> entries = new();
    private readonly Dictionary<string, object> index = new(StringComparer.Ordinal);

    public IReadOnlyList<KeyValuePair<string, object>> Entries => entries;

    public bool TryGetValue(string key, out object value) => index.TryGetValue(key, out value!);

    public string? GetString(string key) => index.TryGetValue(key, out var value) ? value as string : null;

    public VdfObject? GetObject(string key) => index.TryGetValue(key, out var value) ? value as VdfObject : null;

    internal bool TryAdd(string key, object value)
    {
        if (index.ContainsKey(key))
        {
            return false;
        }

        index.Add(key, value);
        entries.Add(new KeyValuePair<string, object>(key, value));
        return true;
    }
}
