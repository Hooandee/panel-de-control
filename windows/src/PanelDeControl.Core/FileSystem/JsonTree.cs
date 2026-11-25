using System.Runtime.Serialization.Json;
using System.Text;
using System.Xml;
using System.Xml.Linq;

namespace PanelDeControl.Core.FileSystem;

/// <summary>Untyped JSON for files other tools write, read through the framework's JSON-to-XML reader.</summary>
internal static class JsonTree
{
    public static XElement? Parse(string text)
    {
        try
        {
            var bytes = Encoding.UTF8.GetBytes(text);
            using var reader = JsonReaderWriterFactory.CreateJsonReader(bytes, XmlDictionaryReaderQuotas.Max);
            return XElement.Load(reader);
        }
        catch (XmlException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
        catch (ArgumentException)
        {
            return null;
        }
    }

    public static string Kind(XElement element) => element.Attribute("type")?.Value ?? "string";

    public static bool IsObject(XElement element) => Kind(element) == "object";

    public static bool IsArray(XElement element) => Kind(element) == "array";

    public static bool IsString(XElement element) => Kind(element) == "string";

    /// <summary>A member's key: names that are not valid XML arrive in an <c>item</c> attribute.</summary>
    public static string Key(XElement member) => member.Attribute("item")?.Value ?? member.Name.LocalName;

    public static XElement? Member(XElement objectElement, string key) =>
        objectElement.Elements().FirstOrDefault(member => Key(member) == key);
}
