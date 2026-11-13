using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>
/// What an install put in a game folder, kept in <c>.pdc-upscaler/manifest.json</c> with the same fields and order
/// the Linux backend writes. A file's hash is null while it is being placed or when Panel rewrites it later (the INI).
/// </summary>
public sealed class GameManifest
{
    public const string Folder = ".pdc-upscaler";
    public const string FileName = "manifest.json";

    public List<KeyValuePair<string, string?>> Files { get; } = new();

    public List<string> Backups { get; } = new();

    public List<string> Dirs { get; } = new();

    /// <summary>Recipe configuration files restored key by key; Windows installs never write one yet.</summary>
    public DataValue Configuration { get; set; } = new DataObject(Array.Empty<KeyValuePair<string, DataValue>>());

    public bool Incomplete { get; set; }

    public string? Engine { get; set; }

    public bool HasConfiguration => Configuration is DataObject { Count: > 0 };

    public string? Hash(string relative) => Files.FirstOrDefault(pair => pair.Key == relative).Value;

    public bool Owns(string relative) => Files.Any(pair => pair.Key == relative);

    public void Set(string relative, string? hash)
    {
        var index = Files.FindIndex(pair => pair.Key == relative);
        if (index >= 0)
        {
            Files[index] = new KeyValuePair<string, string?>(relative, hash);
        }
        else
        {
            Files.Add(new KeyValuePair<string, string?>(relative, hash));
        }
    }

    public static GameManifest? Parse(string text)
    {
        DataObject document;
        try
        {
            document = DataValue.Parse(text) as DataObject ?? throw new DataFormatException("not_object");
        }
        catch (DataFormatException)
        {
            return null;
        }
        var manifest = new GameManifest();
        if (document.Get("files") is DataObject files)
        {
            foreach (var member in files.Members)
            {
                manifest.Files.Add(new KeyValuePair<string, string?>(member.Key, (member.Value as DataString)?.Value));
            }
        }
        manifest.Backups.AddRange(Strings(document.Get("backups")));
        manifest.Dirs.AddRange(Strings(document.Get("dirs")));
        if (document.Get("configuration") is { } configuration)
        {
            manifest.Configuration = configuration;
        }
        manifest.Incomplete = document.Get("incomplete") is DataBool { Value: true };
        manifest.Engine = (document.Get("engine") as DataString)?.Value;
        return manifest;
    }

    public string ToJson()
    {
        var members = new List<KeyValuePair<string, DataValue>>
        {
            Member("files", new DataObject(Files.Select(pair => Member(pair.Key, pair.Value is null ? DataNull.Instance : new DataString(pair.Value))).ToList())),
            Member("backups", new DataArray(Backups.Select(name => (DataValue)new DataString(name)).ToList())),
            Member("dirs", new DataArray(Dirs.Select(name => (DataValue)new DataString(name)).ToList())),
            Member("configuration", Configuration),
        };
        if (Incomplete)
        {
            members.Add(Member("incomplete", new DataBool(true)));
        }
        if (Engine is not null)
        {
            members.Add(Member("engine", new DataString(Engine)));
        }
        return PythonJson.Write(new DataObject(members));
    }

    private static KeyValuePair<string, DataValue> Member(string key, DataValue value) => new(key, value);

    private static IEnumerable<string> Strings(DataValue? value) =>
        value is DataArray array ? array.Items.OfType<DataString>().Select(item => item.Value) : Enumerable.Empty<string>();
}
