using System.Text;

namespace PanelDeControl.Core.FileSystem;

/// <summary>
/// String rules of the Linux backend, which is the reference for every detection answer: Python's
/// whitespace, line breaks, decimal digits and int() differ from .NET's in small but observable ways.
/// </summary>
internal static class PythonText
{
    public static bool IsWhiteSpace(char value) =>
        char.IsWhiteSpace(value) || (value >= '\x1c' && value <= '\x1f');

    public static string Strip(string value)
    {
        var start = 0;
        var end = value.Length;
        while (start < end && IsWhiteSpace(value[start]))
        {
            start++;
        }

        while (end > start && IsWhiteSpace(value[end - 1]))
        {
            end--;
        }

        return value.Substring(start, end - start);
    }

    public static IReadOnlyList<string> SplitLines(string value)
    {
        var lines = new List<string>();
        var start = 0;
        var index = 0;
        while (index < value.Length)
        {
            var current = value[index];
            if (IsLineBreak(current))
            {
                lines.Add(value.Substring(start, index - start));
                index += current == '\r' && index + 1 < value.Length && value[index + 1] == '\n' ? 2 : 1;
                start = index;
                continue;
            }

            index++;
        }

        if (start < value.Length)
        {
            lines.Add(value.Substring(start));
        }

        return lines;
    }

    public static bool IsDecimal(string value) => value.Length > 0 && value.All(char.IsDigit);

    /// <summary>Python's int() on text: surrounding whitespace, a sign, any decimal digits, single '_' between digits.</summary>
    public static bool TryParseInteger(string text, out long value)
    {
        value = 0;
        var trimmed = Strip(text);
        var index = 0;
        var negative = false;
        if (index < trimmed.Length && (trimmed[index] == '+' || trimmed[index] == '-'))
        {
            negative = trimmed[index] == '-';
            index++;
        }

        if (index >= trimmed.Length)
        {
            return false;
        }

        var previousDigit = false;
        long result = 0;
        for (; index < trimmed.Length; index++)
        {
            var current = trimmed[index];
            if (current == '_')
            {
                if (!previousDigit || index + 1 >= trimmed.Length || !char.IsDigit(trimmed[index + 1]))
                {
                    return false;
                }

                previousDigit = false;
                continue;
            }

            if (!char.IsDigit(current))
            {
                return false;
            }

            try
            {
                result = checked((result * 10) + (long)char.GetNumericValue(current));
            }
            catch (OverflowException)
            {
                return false;
            }

            previousDigit = true;
        }

        value = negative ? -result : result;
        return true;
    }

    /// <summary>ASCII with every byte above 0x7F turned into U+FFFD, then lower-cased.</summary>
    public static string LowerAscii(byte[] data, int offset, int count)
    {
        var builder = new StringBuilder(count);
        for (var index = offset; index < offset + count; index++)
        {
            var current = data[index];
            builder.Append(current < 0x80 ? char.ToLowerInvariant((char)current) : '\uFFFD');
        }

        return builder.ToString();
    }

    /// <summary>UTF-16LE where an odd trailing byte or an unpaired surrogate becomes U+FFFD.</summary>
    public static string Utf16(byte[] data, int offset, int count)
    {
        var builder = new StringBuilder(count / 2 + 1);
        var end = offset + count;
        var index = offset;
        while (index + 1 < end)
        {
            var unit = (char)(data[index] | (data[index + 1] << 8));
            index += 2;
            if (char.IsHighSurrogate(unit) && index + 1 < end)
            {
                var next = (char)(data[index] | (data[index + 1] << 8));
                if (char.IsLowSurrogate(next))
                {
                    builder.Append(unit).Append(next);
                    index += 2;
                    continue;
                }
            }

            builder.Append(char.IsSurrogate(unit) ? '\uFFFD' : unit);
        }

        if (index < end)
        {
            builder.Append('\uFFFD');
        }

        return builder.ToString();
    }

    public static int? ParseDigits(string digits)
    {
        long result = 0;
        foreach (var current in digits)
        {
            result = (result * 10) + (long)char.GetNumericValue(current);
            if (result > int.MaxValue)
            {
                return null;
            }
        }

        return (int)result;
    }

    private static bool IsLineBreak(char value) =>
        value is '\n' or '\r' or '\x0b' or '\x0c' or '\x1c' or '\x1d' or '\x1e' or '\x85' or '\u2028' or '\u2029';
}
