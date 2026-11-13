using System.Globalization;
using System.Text;

namespace PanelDeControl.Core.Data;

/// <summary>Text exactly as Python's <c>json.dumps</c> writes it with its defaults, so both systems write the same files.</summary>
public static class PythonJson
{
    public static string Write(DataValue value)
    {
        var text = new StringBuilder();
        Append(text, value);
        return text.ToString();
    }

    private static void Append(StringBuilder text, DataValue value)
    {
        switch (value)
        {
            case DataObject data:
                text.Append('{');
                for (var index = 0; index < data.Members.Count; index++)
                {
                    if (index > 0)
                    {
                        text.Append(", ");
                    }
                    Quote(text, data.Members[index].Key);
                    text.Append(": ");
                    Append(text, data.Members[index].Value);
                }
                text.Append('}');
                break;
            case DataArray array:
                text.Append('[');
                for (var index = 0; index < array.Items.Count; index++)
                {
                    if (index > 0)
                    {
                        text.Append(", ");
                    }
                    Append(text, array.Items[index]);
                }
                text.Append(']');
                break;
            case DataString data:
                Quote(text, data.Value);
                break;
            case DataNumber number:
                text.Append(number.Integer is { } integer
                    ? integer.ToString(CultureInfo.InvariantCulture)
                    : number.Real.ToString("R", CultureInfo.InvariantCulture));
                break;
            case DataBool flag:
                text.Append(flag.Value ? "true" : "false");
                break;
            default:
                text.Append("null");
                break;
        }
    }

    private static void Quote(StringBuilder text, string value)
    {
        text.Append('"');
        foreach (var character in value)
        {
            switch (character)
            {
                case '"': text.Append("\\\""); break;
                case '\\': text.Append("\\\\"); break;
                case '\n': text.Append("\\n"); break;
                case '\r': text.Append("\\r"); break;
                case '\t': text.Append("\\t"); break;
                case '\b': text.Append("\\b"); break;
                case '\f': text.Append("\\f"); break;
                default:
                    if (character < 0x20 || character > 0x7e)
                    {
                        text.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        text.Append(character);
                    }
                    break;
            }
        }
        text.Append('"');
    }
}
