using System.Globalization;
using System.Numerics;
using System.Text;

namespace PanelDeControl.Core.Data;

/// <summary>A JSON value read with the same rules as Python's json module, which the Linux backend uses.</summary>
public abstract class DataValue
{
    public static DataValue Parse(byte[] utf8)
    {
        string text;
        try
        {
            text = new UTF8Encoding(false, true).GetString(utf8);
        }
        catch (DecoderFallbackException)
        {
            throw new DataFormatException("invalid_json");
        }
        return Parse(text);
    }

    public static DataValue Parse(string text) => new DataReader(text).ReadDocument();
}

public sealed class DataObject : DataValue
{
    public DataObject(IReadOnlyList<KeyValuePair<string, DataValue>> members)
    {
        Members = members;
    }

    /// <summary>Members in document order.</summary>
    public IReadOnlyList<KeyValuePair<string, DataValue>> Members { get; }

    public IEnumerable<string> Keys => Members.Select(member => member.Key);

    public int Count => Members.Count;

    public bool Has(string key) => Members.Any(member => member.Key == key);

    public DataValue? Get(string key)
    {
        foreach (var member in Members)
        {
            if (member.Key == key)
            {
                return member.Value;
            }
        }
        return null;
    }
}

public sealed class DataArray : DataValue
{
    public DataArray(IReadOnlyList<DataValue> items)
    {
        Items = items;
    }

    public IReadOnlyList<DataValue> Items { get; }
}

public sealed class DataString : DataValue
{
    public DataString(string value)
    {
        Value = value;
    }

    public string Value { get; }
}

public sealed class DataNumber : DataValue
{
    public DataNumber(BigInteger? integer, double real)
    {
        Integer = integer;
        Real = real;
    }

    /// <summary>Set when the literal has no fraction or exponent: Python reads it as an int.</summary>
    public BigInteger? Integer { get; }

    public double Real { get; }
}

public sealed class DataBool : DataValue
{
    public DataBool(bool value)
    {
        Value = value;
    }

    public bool Value { get; }
}

public sealed class DataNull : DataValue
{
    public static readonly DataNull Instance = new();

    private DataNull()
    {
    }
}

public sealed class DataFormatException : Exception
{
    public DataFormatException(string code)
        : base(code)
    {
        Code = code;
    }

    public string Code { get; }
}

internal sealed class DataReader
{
    private readonly string _text;
    private int _position;

    public DataReader(string text)
    {
        _text = text;
    }

    public DataValue ReadDocument()
    {
        SkipWhitespace();
        var value = ReadValue();
        SkipWhitespace();
        if (_position != _text.Length)
        {
            throw Invalid();
        }
        return value;
    }

    private static DataFormatException Invalid() => new("invalid_json");

    private void SkipWhitespace()
    {
        while (_position < _text.Length && _text[_position] is ' ' or '\t' or '\n' or '\r')
        {
            _position++;
        }
    }

    private DataValue ReadValue()
    {
        if (_position >= _text.Length)
        {
            throw Invalid();
        }
        switch (_text[_position])
        {
            case '{':
                return ReadObject();
            case '[':
                return ReadArray();
            case '"':
                return new DataString(ReadString());
        }
        if (Consume("true"))
        {
            return new DataBool(true);
        }
        if (Consume("false"))
        {
            return new DataBool(false);
        }
        if (Consume("null"))
        {
            return DataNull.Instance;
        }
        if (Consume("NaN"))
        {
            return new DataNumber(null, double.NaN);
        }
        if (Consume("Infinity"))
        {
            return new DataNumber(null, double.PositiveInfinity);
        }
        if (Consume("-Infinity"))
        {
            return new DataNumber(null, double.NegativeInfinity);
        }
        return ReadNumber();
    }

    private bool Consume(string literal)
    {
        if (string.CompareOrdinal(_text, _position, literal, 0, literal.Length) != 0)
        {
            return false;
        }
        _position += literal.Length;
        return true;
    }

    private DataObject ReadObject()
    {
        _position++;
        var members = new List<KeyValuePair<string, DataValue>>();
        SkipWhitespace();
        if (_position < _text.Length && _text[_position] == '}')
        {
            _position++;
            return new DataObject(members);
        }
        while (true)
        {
            SkipWhitespace();
            if (_position >= _text.Length || _text[_position] != '"')
            {
                throw Invalid();
            }
            var key = ReadString();
            SkipWhitespace();
            if (_position >= _text.Length || _text[_position] != ':')
            {
                throw Invalid();
            }
            _position++;
            SkipWhitespace();
            members.Add(new KeyValuePair<string, DataValue>(key, ReadValue()));
            SkipWhitespace();
            if (_position >= _text.Length)
            {
                throw Invalid();
            }
            var separator = _text[_position++];
            if (separator == '}')
            {
                break;
            }
            if (separator != ',')
            {
                throw Invalid();
            }
        }
        if (members.Select(member => member.Key).Distinct(StringComparer.Ordinal).Count() != members.Count)
        {
            throw new DataFormatException("duplicate_key");
        }
        return new DataObject(members);
    }

    private DataArray ReadArray()
    {
        _position++;
        var items = new List<DataValue>();
        SkipWhitespace();
        if (_position < _text.Length && _text[_position] == ']')
        {
            _position++;
            return new DataArray(items);
        }
        while (true)
        {
            SkipWhitespace();
            items.Add(ReadValue());
            SkipWhitespace();
            if (_position >= _text.Length)
            {
                throw Invalid();
            }
            var separator = _text[_position++];
            if (separator == ']')
            {
                return new DataArray(items);
            }
            if (separator != ',')
            {
                throw Invalid();
            }
        }
    }

    private string ReadString()
    {
        _position++;
        var builder = new StringBuilder();
        while (true)
        {
            if (_position >= _text.Length)
            {
                throw Invalid();
            }
            var character = _text[_position++];
            if (character == '"')
            {
                return builder.ToString();
            }
            if (character < ' ')
            {
                throw Invalid();
            }
            if (character != '\\')
            {
                builder.Append(character);
                continue;
            }
            if (_position >= _text.Length)
            {
                throw Invalid();
            }
            var escape = _text[_position++];
            switch (escape)
            {
                case '"': builder.Append('"'); break;
                case '\\': builder.Append('\\'); break;
                case '/': builder.Append('/'); break;
                case 'b': builder.Append('\b'); break;
                case 'f': builder.Append('\f'); break;
                case 'n': builder.Append('\n'); break;
                case 'r': builder.Append('\r'); break;
                case 't': builder.Append('\t'); break;
                case 'u':
                    if (_position + 4 > _text.Length
                        || !int.TryParse(_text.Substring(_position, 4), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var code))
                    {
                        throw Invalid();
                    }
                    builder.Append((char)code);
                    _position += 4;
                    break;
                default:
                    throw Invalid();
            }
        }
    }

    private DataNumber ReadNumber()
    {
        var start = _position;
        if (_position < _text.Length && _text[_position] == '-')
        {
            _position++;
        }
        if (_position >= _text.Length || !IsDigit(_text[_position]))
        {
            throw Invalid();
        }
        if (_text[_position] == '0')
        {
            _position++;
        }
        else
        {
            SkipDigits();
        }
        var integral = true;
        if (_position + 1 < _text.Length && _text[_position] == '.' && IsDigit(_text[_position + 1]))
        {
            integral = false;
            _position++;
            SkipDigits();
        }
        if (_position < _text.Length && _text[_position] is 'e' or 'E')
        {
            var mark = _position;
            _position++;
            if (_position < _text.Length && _text[_position] is '+' or '-')
            {
                _position++;
            }
            if (_position < _text.Length && IsDigit(_text[_position]))
            {
                integral = false;
                SkipDigits();
            }
            else
            {
                _position = mark;
            }
        }
        var literal = _text.Substring(start, _position - start);
        var real = double.Parse(literal, NumberStyles.Float, CultureInfo.InvariantCulture);
        return new DataNumber(integral ? BigInteger.Parse(literal, CultureInfo.InvariantCulture) : null, real);
    }

    private void SkipDigits()
    {
        while (_position < _text.Length && IsDigit(_text[_position]))
        {
            _position++;
        }
    }

    private static bool IsDigit(char character) => character is >= '0' and <= '9';
}
