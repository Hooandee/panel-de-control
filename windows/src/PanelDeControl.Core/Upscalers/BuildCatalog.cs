using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

public sealed class UpscalerAsset
{
    public UpscalerAsset(string id, string fileName, string sha256, long size, IReadOnlyList<string> urls, bool archive, string? member, int generation)
    {
        Id = id;
        FileName = fileName;
        Sha256 = sha256;
        Size = size;
        Urls = urls;
        Archive = archive;
        Member = member;
        Generation = generation;
    }

    public string Id { get; }

    public string FileName { get; }

    public string Sha256 { get; }

    public long Size { get; }

    public IReadOnlyList<string> Urls { get; }

    public bool Archive { get; }

    public string? Member { get; }

    public int Generation { get; }
}

public sealed class UpscalerModel
{
    public UpscalerModel(string id, IReadOnlyDictionary<string, string> ini)
    {
        Id = id;
        Ini = ini;
    }

    public string Id { get; }

    public IReadOnlyDictionary<string, string> Ini { get; }
}

public sealed class UpscalerBuild
{
    internal UpscalerBuild()
    {
    }

    public string Id { get; internal set; } = "";

    public string Family { get; internal set; } = "";

    public string Version { get; internal set; } = "";

    public IReadOnlyList<string> Gpus { get; internal set; } = Array.Empty<string>();

    public long Image { get; internal set; }

    public long Cost { get; internal set; }

    public IReadOnlyList<string> Assets { get; internal set; } = Array.Empty<string>();

    public IReadOnlyDictionary<string, string> Replace { get; internal set; } = new Dictionary<string, string>();

    public IReadOnlyDictionary<string, string> Ini { get; internal set; } = new Dictionary<string, string>();

    public string? Injector { get; internal set; }

    public bool Available { get; internal set; } = true;

    public string Archive { get; internal set; } = "";

    public string Channel { get; internal set; } = "stable";

    public string ExtraDir { get; internal set; } = "";

    /// <summary>The first model is the default.</summary>
    public IReadOnlyList<UpscalerModel> Models { get; internal set; } = Array.Empty<UpscalerModel>();

    public string Engine { get; internal set; } = "optiscaler";

    public string Way { get; internal set; } = "";

    public IReadOnlyDictionary<string, string> LegacyReplace { get; internal set; } = new Dictionary<string, string>();
}

/// <summary>
/// The neutral build catalog (<c>shared/upscalers/catalog.json</c>), read with the same rules and error codes as
/// <c>py_modules/upscalers/catalog.py</c>.
/// </summary>
public sealed class BuildCatalog
{
    private static readonly string[] ArchiveRoles = { "optiscaler", "optiscaler_beta", "lsfg", "helixsr", "optipatcher" };

    private BuildCatalog()
    {
    }

    public IReadOnlyDictionary<string, string> Archives { get; private set; } = new Dictionary<string, string>();

    public IReadOnlyList<string> Amd { get; private set; } = Array.Empty<string>();

    public IReadOnlyList<string> EveryGpu { get; private set; } = Array.Empty<string>();

    /// <summary>Assets in catalog order.</summary>
    public IReadOnlyList<UpscalerAsset> Assets { get; private set; } = Array.Empty<UpscalerAsset>();

    /// <summary>Builds in catalog order, which is the order shown to the user.</summary>
    public IReadOnlyList<UpscalerBuild> Builds { get; private set; } = Array.Empty<UpscalerBuild>();

    public IReadOnlyDictionary<string, string> Preferred { get; private set; } = new Dictionary<string, string>();

    public IReadOnlyDictionary<string, double> QualityRatios { get; private set; } = new Dictionary<string, double>();

    public IReadOnlyDictionary<string, string> EasyModes { get; private set; } = new Dictionary<string, string>();

    public IReadOnlyDictionary<string, double?> Sharpness { get; private set; } = new Dictionary<string, double?>();

    public IReadOnlyList<string> Proxies { get; private set; } = Array.Empty<string>();

    public IReadOnlyDictionary<string, string> BaseIni { get; private set; } = new Dictionary<string, string>();

    public string FfxLoader { get; private set; } = "";

    public static BuildCatalog Parse(byte[] utf8) => Parse(DataValue.Parse(utf8));

    public static BuildCatalog Parse(string json) => Parse(DataValue.Parse(json));

    private static BuildCatalog Parse(DataValue document)
    {
        var raw = Fields(document, new[] { "schema_version", "archives", "gpu_groups", "preferred", "quality_ratios", "easy_modes",
            "sharpness", "proxies", "base_ini", "ffx_loader", "assets", "builds" }, new[] { "notes" });
        if (!(raw.Get("schema_version") is DataNumber { Integer: { } version } && version == 1))
        {
            throw new DataFormatException("unsupported_schema");
        }
        var groups = Fields(raw.Get("gpu_groups")!, new[] { "amd", "every" });
        var archives = Fields(raw.Get("archives")!, ArchiveRoles);
        Check(archives.Members.All(member => member.Value is DataString { Value.Length: > 0 }), "invalid_archives");
        var assetItems = Items(raw.Get("assets")!);
        var buildItems = Items(raw.Get("builds")!);
        var assets = assetItems.Select(ReadAsset).ToList();
        var builds = buildItems.Select(ReadBuild).ToList();
        var assetIds = new HashSet<string>(assets.Select(asset => asset.Id), StringComparer.Ordinal);
        var buildIds = new HashSet<string>(builds.Select(build => build.Id), StringComparer.Ordinal);
        Check(assetIds.Count == assets.Count && buildIds.Count == builds.Count, "duplicate_id");
        foreach (var build in builds)
        {
            var referenced = build.Assets.Concat(build.Replace.Values).Concat(build.LegacyReplace.Values).Append(build.Archive)
                .Concat(build.Injector is { Length: > 0 } injector ? new[] { injector } : Array.Empty<string>());
            Check(referenced.All(assetIds.Contains), "missing_asset");
        }
        var archiveMap = archives.Members.ToDictionary(member => member.Key, member => ((DataString)member.Value).Value, StringComparer.Ordinal);
        Check(archiveMap.Values.All(assetIds.Contains), "missing_asset");
        var preferred = Mapping(raw.Get("preferred")!);
        Check(preferred.Values.All(buildIds.Contains), "missing_build");
        Check(raw.Get("ffx_loader") is DataString { Value.Length: > 0 }, "invalid_ffx_loader");
        return new BuildCatalog
        {
            Amd = Strings(groups.Get("amd")!),
            EveryGpu = Strings(groups.Get("every")!),
            Archives = archiveMap,
            Assets = assets,
            Builds = builds,
            Preferred = preferred,
            QualityRatios = Numbers(raw.Get("quality_ratios")!, allowNull: false).ToDictionary(pair => pair.Key, pair => pair.Value!.Value, StringComparer.Ordinal),
            EasyModes = Mapping(raw.Get("easy_modes")!),
            Sharpness = Numbers(raw.Get("sharpness")!, allowNull: true),
            Proxies = Strings(raw.Get("proxies")!),
            BaseIni = Mapping(raw.Get("base_ini")!),
            FfxLoader = ((DataString)raw.Get("ffx_loader")!).Value,
        };
    }

    public UpscalerBuild? Build(string id) => Builds.FirstOrDefault(build => build.Id == id);

    public UpscalerAsset? Asset(string id) => Assets.FirstOrDefault(asset => asset.Id == id);

    private static UpscalerAsset ReadAsset(DataValue value)
    {
        var item = Fields(value, new[] { "id", "filename", "sha256", "size", "urls" }, new[] { "archive", "member", "generation", "note" });
        Check(item.Get("size") is DataNumber { Integer: { } size } && size > 0
              && (item.Get("generation") is null || item.Get("generation") is DataNumber { Integer: not null }), "invalid_asset");
        Check((item.Get("archive") is null || item.Get("archive") is DataBool)
              && (item.Get("member") is null || item.Get("member") is DataString), "invalid_asset");
        Check(item.Get("sha256") is DataString { Value: var sha } && sha.Length == 64 && sha.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'),
            "invalid_sha256");
        return new UpscalerAsset(
            Text(item.Get("id")!),
            Text(item.Get("filename")!),
            ((DataString)item.Get("sha256")!).Value,
            (long)((DataNumber)item.Get("size")!).Integer!.Value,
            Strings(item.Get("urls")!),
            item.Get("archive") is DataBool { Value: true },
            (item.Get("member") as DataString)?.Value,
            item.Get("generation") is DataNumber { Integer: { } generation } ? (int)generation : 9);
    }

    private static UpscalerBuild ReadBuild(DataValue value)
    {
        var item = Fields(value, new[] { "id", "family", "version", "engine", "gpus", "image", "cost", "archive" },
            new[] { "way", "channel", "available", "extra_dir", "assets", "injector", "replace", "legacy_replace", "ini", "models", "note" });
        Check(item.Get("image") is DataNumber { Integer: not null } && item.Get("cost") is DataNumber { Integer: not null }
              && (item.Get("available") is null || item.Get("available") is DataBool), "invalid_build");
        Check(new[] { "channel", "extra_dir", "way", "injector" }.All(key => item.Get(key) is null or DataString), "invalid_build");
        var models = item.Get("models") ?? new DataArray(Array.Empty<DataValue>());
        Check(models is DataArray, "invalid_models");
        var build = new UpscalerBuild
        {
            Id = Text(item.Get("id")!),
            Family = Text(item.Get("family")!),
            Version = Text(item.Get("version")!),
            Gpus = Strings(item.Get("gpus")!),
            Image = (long)((DataNumber)item.Get("image")!).Integer!.Value,
            Cost = (long)((DataNumber)item.Get("cost")!).Integer!.Value,
        };
        build.Assets = Strings(item.Get("assets") ?? new DataArray(Array.Empty<DataValue>()));
        build.Replace = Mapping(item.Get("replace") ?? new DataObject(Array.Empty<KeyValuePair<string, DataValue>>()));
        build.Ini = Mapping(item.Get("ini") ?? new DataObject(Array.Empty<KeyValuePair<string, DataValue>>()));
        build.Injector = (item.Get("injector") as DataString)?.Value;
        build.Available = item.Get("available") is not DataBool { Value: false };
        build.Archive = Text(item.Get("archive")!);
        build.Channel = (item.Get("channel") as DataString)?.Value ?? "stable";
        build.ExtraDir = (item.Get("extra_dir") as DataString)?.Value ?? "";
        build.Models = ((DataArray)models).Items
            .Select(model => Fields(model, new[] { "id", "ini" }))
            .Select(model => new UpscalerModel(Text(model.Get("id")!), Mapping(model.Get("ini")!)))
            .ToList();
        build.Engine = Text(item.Get("engine")!);
        build.Way = (item.Get("way") as DataString)?.Value ?? "";
        build.LegacyReplace = Mapping(item.Get("legacy_replace") ?? new DataObject(Array.Empty<KeyValuePair<string, DataValue>>()));
        return build;
    }

    private static void Check(bool condition, string code)
    {
        if (!condition)
        {
            throw new DataFormatException(code);
        }
    }

    internal static DataObject Fields(DataValue value, IReadOnlyCollection<string> required, IReadOnlyCollection<string>? optional = null)
    {
        if (value is not DataObject item || !required.All(item.Has)
            || item.Keys.Any(key => !required.Contains(key) && !(optional?.Contains(key) ?? false)))
        {
            throw new DataFormatException("invalid_fields");
        }
        return item;
    }

    /// <summary>Python iterates a JSON object's keys when a list is expected, and each key then fails as a record.</summary>
    private static IReadOnlyList<DataValue> Items(DataValue value) => value switch
    {
        DataArray array => array.Items,
        DataObject item => item.Keys.Select(key => (DataValue)new DataString(key)).ToList(),
        _ => throw new DataFormatException("invalid_fields"),
    };

    private static string Text(DataValue value)
    {
        Check(value is DataString { Value.Length: > 0 }, "invalid_text");
        return ((DataString)value).Value;
    }

    private static IReadOnlyList<string> Strings(DataValue value)
    {
        Check(value is DataArray array && array.Items.All(item => item is DataString { Value.Length: > 0 }), "invalid_list");
        return ((DataArray)value).Items.Select(item => ((DataString)item).Value).ToList();
    }

    private static IReadOnlyDictionary<string, string> Mapping(DataValue value)
    {
        Check(value is DataObject item && item.Members.All(member => member.Value is DataString), "invalid_mapping");
        return ((DataObject)value).Members.ToDictionary(member => member.Key, member => ((DataString)member.Value).Value, StringComparer.Ordinal);
    }

    private static IReadOnlyDictionary<string, double?> Numbers(DataValue value, bool allowNull)
    {
        Check(value is DataObject item && item.Members.All(member => member.Value is DataNumber || (allowNull && member.Value is DataNull)),
            "invalid_mapping");
        return ((DataObject)value).Members.ToDictionary(
            member => member.Key,
            member => member.Value is DataNumber number ? number.Real : (double?)null,
            StringComparer.Ordinal);
    }
}
