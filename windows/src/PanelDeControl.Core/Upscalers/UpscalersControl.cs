using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Upscalers;

[DataContract]
public enum UpscalersOperation
{
    [EnumMember(Value = "overview")]
    Overview = 0,

    [EnumMember(Value = "game")]
    Game = 1,

    [EnumMember(Value = "install")]
    Install = 2,

    [EnumMember(Value = "uninstall")]
    Uninstall = 3,

    [EnumMember(Value = "job")]
    Job = 4,

    [EnumMember(Value = "cover")]
    Cover = 5,

    /// <summary>Reads the in-game badge's mode, or sets it when the request carries one.</summary>
    [EnumMember(Value = "ingame")]
    InGame = 6,
}

[DataContract]
public enum UpscalersResponseStatus
{
    [EnumMember(Value = "ok")]
    Ok = 0,

    [EnumMember(Value = "rejected")]
    Rejected = 1,

    [EnumMember(Value = "fault")]
    Fault = 2,
}

/// <summary>What Panel knows of one game's upscaler: <c>none</c>, <c>installed</c>, <c>missing</c>, <c>foreign</c> or <c>panel_unknown</c>.</summary>
public static class UpscalerGameStates
{
    public const string None = "none";
    public const string Installed = "installed";
    public const string Missing = "missing";
    public const string Foreign = "foreign";

    /// <summary>Panel's files are there (complete manifest) but the record of which build was lost.</summary>
    public const string PanelUnknown = "panel_unknown";
}

[DataContract]
public sealed class UpscalersRequest
{
    public const int MaximumFieldLength = 64;
    public const int MaximumAppIdLength = 20;

    private UpscalersRequest()
    {
    }

    private UpscalersRequest(UpscalersOperation operation, string? appId = null, string? build = null, string? quality = null, string? model = null, bool? experimental = null)
    {
        Operation = operation;
        AppId = appId;
        Build = build;
        Quality = quality;
        Model = model;
        Experimental = experimental;
    }

    private static readonly string[] FrameGenRoutes = { "game", "optiscaler", "anr" };

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public UpscalersOperation Operation { get; private set; }

    [DataMember(Name = "appid", Order = 2, EmitDefaultValue = false)]
    public string? AppId { get; private set; }

    [DataMember(Name = "build", Order = 3, EmitDefaultValue = false)]
    public string? Build { get; private set; }

    [DataMember(Name = "quality", Order = 4, EmitDefaultValue = false)]
    public string? Quality { get; private set; }

    [DataMember(Name = "model", Order = 5, EmitDefaultValue = false)]
    public string? Model { get; private set; }

    /// <summary>Set by the widget when the user opted into experimental features; install and uninstall need it.</summary>
    [DataMember(Name = "experimental", Order = 6, EmitDefaultValue = false)]
    public bool? Experimental { get; private set; }

    [DataMember(Name = "sharpness", Order = 7, EmitDefaultValue = false)]
    public string? Sharpness { get; private set; }

    /// <summary>Frame generation on, through <see cref="FrameGenRoute"/> (<c>game</c>, <c>optiscaler</c> or <c>anr</c>).</summary>
    [DataMember(Name = "fg", Order = 8, EmitDefaultValue = false)]
    public bool? FrameGen { get; private set; }

    [DataMember(Name = "fg_route", Order = 9, EmitDefaultValue = false)]
    public string? FrameGenRoute { get; private set; }

    /// <summary>The in-game badge mode to set: <c>off</c>, <c>start</c> or <c>always</c>.</summary>
    [DataMember(Name = "mode", Order = 10, EmitDefaultValue = false)]
    public string? Mode { get; private set; }

    public static UpscalersRequest Overview() => new(UpscalersOperation.Overview);

    public static UpscalersRequest Game(string appId) => new(UpscalersOperation.Game, appId: appId);

    public static UpscalersRequest Job() => new(UpscalersOperation.Job);

    /// <summary>Asks for the in-game badge's mode; with <paramref name="mode"/> it sets it first.</summary>
    public static UpscalersRequest InGame(string? mode = null) => new(UpscalersOperation.InGame) { Mode = mode };

    public static UpscalersRequest Cover(string appId) => new(UpscalersOperation.Cover, appId: appId);

    public static UpscalersRequest Install(string appId, string build, string? quality, string? model, bool experimental,
        string? sharpness = null, bool frameGen = false, string? frameGenRoute = null) =>
        new(UpscalersOperation.Install, appId, build, quality, model, experimental)
        {
            Sharpness = sharpness,
            FrameGen = frameGen ? true : null,
            FrameGenRoute = frameGenRoute,
        };

    public static UpscalersRequest Uninstall(string appId, bool experimental) =>
        new(UpscalersOperation.Uninstall, appId, experimental: experimental);

    public bool ExperimentalEnabled => Experimental == true;

    internal void Validate()
    {
        bool Absent(string? field) => field is null;
        bool Token(string? field) => field is { Length: > 0 and <= MaximumFieldLength } && field.All(IsTokenCharacter);
        bool Optional(string? field) => field is null || Token(field);
        var noFrameGen = Absent(Sharpness) && FrameGen is null && Absent(FrameGenRoute) && Absent(Mode);
        var appId = AppId is { Length: > 0 and <= MaximumAppIdLength } && AppId.All(character => character is >= '0' and <= '9');
        var valid = Operation switch
        {
            UpscalersOperation.Overview or UpscalersOperation.Job =>
                Absent(AppId) && Absent(Build) && Absent(Quality) && Absent(Model) && Experimental is null && noFrameGen,
            UpscalersOperation.Game or UpscalersOperation.Cover => appId && Absent(Build) && Absent(Quality) && Absent(Model) && Experimental is null && noFrameGen,
            UpscalersOperation.Install => appId && Token(Build) && Optional(Quality) && Optional(Model) && Optional(Sharpness) && Absent(Mode)
                && (FrameGenRoute is null || Array.IndexOf(FrameGenRoutes, FrameGenRoute) >= 0),
            UpscalersOperation.Uninstall => appId && Absent(Build) && Absent(Quality) && Absent(Model) && noFrameGen,
            UpscalersOperation.InGame =>
                Absent(AppId) && Absent(Build) && Absent(Quality) && Absent(Model) && Experimental is null
                && Absent(Sharpness) && FrameGen is null && Absent(FrameGenRoute) && (Mode is null || InGameModes.IsValid(Mode)),
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("Upscalers request is invalid.");
        }
    }

    private static bool IsTokenCharacter(char character) =>
        character is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or >= '0' and <= '9' or '.' or '_' or '-' or '+';
}

[DataContract]
public sealed class UpscalerGameSummary
{
    [DataMember(Name = "appid", Order = 1, IsRequired = true)]
    public string AppId { get; set; } = "";

    [DataMember(Name = "name", Order = 2, IsRequired = true)]
    public string Name { get; set; } = "";

    [DataMember(Name = "state", Order = 3, IsRequired = true)]
    public string State { get; set; } = UpscalerGameStates.None;

    [DataMember(Name = "build", Order = 4, EmitDefaultValue = false)]
    public string? Build { get; set; }

    [DataMember(Name = "version", Order = 5, EmitDefaultValue = false)]
    public string? Version { get; set; }

    /// <summary>Absent when the process list could not be read in time.</summary>
    [DataMember(Name = "running", Order = 6, EmitDefaultValue = false)]
    public bool? Running { get; set; }

    [DataMember(Name = "updating", Order = 7, IsRequired = true)]
    public bool Updating { get; set; }

    /// <summary>False when the folder scan for another tool's upscaler did not finish in time: <c>none</c> is then unconfirmed.</summary>
    [DataMember(Name = "scanned", Order = 8, IsRequired = true)]
    public bool Scanned { get; set; } = true;

    /// <summary>What the installed build is called, as the Linux pill says it (<c>FSR 4.1.2 Lite</c>): never the build id.</summary>
    [DataMember(Name = "label", Order = 9, EmitDefaultValue = false)]
    public string? Label { get; set; }
}

[DataContract]
public sealed class UpscalersOverview
{
    [DataMember(Name = "gpu", Order = 1, IsRequired = true)]
    public string Gpu { get; set; } = "unknown";

    [DataMember(Name = "gpu_source", Order = 2, IsRequired = true)]
    public string GpuSource { get; set; } = "unknown";

    [DataMember(Name = "device", Order = 3, EmitDefaultValue = false)]
    public string? Device { get; set; }

    [DataMember(Name = "steam_found", Order = 4, IsRequired = true)]
    public bool SteamFound { get; set; }

    [DataMember(Name = "games", Order = 5, IsRequired = true)]
    public UpscalerGameSummary[] Games { get; set; } = new UpscalerGameSummary[0];

    /// <summary>The adapter's own name (<c>NVIDIA GeForce RTX 5090 Laptop GPU</c>); <see cref="Gpu"/> stays the family the rules use.</summary>
    [DataMember(Name = "gpu_name", Order = 6, EmitDefaultValue = false)]
    public string? GpuName { get; set; }

    [DataMember(Name = "ingame", Order = 7, EmitDefaultValue = false)]
    public string? InGame { get; set; }
}

[DataContract]
public sealed class UpscalerInput
{
    [DataMember(Name = "kind", Order = 1, IsRequired = true)]
    public string Kind { get; set; } = "";

    [DataMember(Name = "files", Order = 2, IsRequired = true)]
    public string[] Files { get; set; } = new string[0];
}

[DataContract]
public sealed class UpscalerForeignSummary
{
    [DataMember(Name = "engine", Order = 1, IsRequired = true)]
    public string Engine { get; set; } = "unknown";

    [DataMember(Name = "variant", Order = 2, IsRequired = true)]
    public string Variant { get; set; } = "unknown";

    [DataMember(Name = "manifest_error", Order = 3, IsRequired = true)]
    public bool ManifestError { get; set; }
}

[DataContract]
public sealed class UpscalerRecipeStatus
{
    /// <summary>The recipe's own status (<c>verified</c>, <c>experimental</c>, ...), as the catalog states it.</summary>
    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public string Status { get; set; } = "";

    /// <summary>False when the recipe needs dependencies or configuration Windows installs cannot apply yet.</summary>
    [DataMember(Name = "installable", Order = 2, IsRequired = true)]
    public bool Installable { get; set; }

    [DataMember(Name = "revision", Order = 3, IsRequired = true)]
    public long Revision { get; set; }

    [DataMember(Name = "recommended_build", Order = 4, EmitDefaultValue = false)]
    public string? RecommendedBuild { get; set; }

    /// <summary>What Windows does with each of the recipe's dependencies; warnings never block an install.</summary>
    [DataMember(Name = "dependencies", Order = 5, EmitDefaultValue = false)]
    public UpscalerDependencyStatus[]? Dependencies { get; set; }

    [DataMember(Name = "args", Order = 6, EmitDefaultValue = false)]
    public string[]? Args { get; set; }
}

[DataContract]
public sealed class UpscalerHistoryEntry
{
    [DataMember(Name = "build", Order = 1, IsRequired = true)]
    public string Build { get; set; } = "";

    [DataMember(Name = "at", Order = 2, IsRequired = true)]
    public long At { get; set; }

    /// <summary><c>pending</c>, <c>not_run</c>, <c>loaded</c> or <c>active</c>.</summary>
    [DataMember(Name = "result", Order = 3, IsRequired = true)]
    public string Result { get; set; } = "";

    [DataMember(Name = "label", Order = 4, EmitDefaultValue = false)]
    public string? Label { get; set; }

    [DataMember(Name = "observed", Order = 5, EmitDefaultValue = false)]
    public string? Observed { get; set; }
}

[DataContract]
public sealed class UpscalerDependencyStatus
{
    [DataMember(Name = "id", Order = 1, IsRequired = true)]
    public string Id { get; set; } = "";

    [DataMember(Name = "kind", Order = 2, IsRequired = true)]
    public string Kind { get; set; } = "";

    /// <summary><c>install</c>, <c>satisfied</c>, <c>missing</c>, <c>outdated</c>, <c>not_applicable</c> or <c>user_file</c>.</summary>
    [DataMember(Name = "state", Order = 3, IsRequired = true)]
    public string State { get; set; } = "";

    [DataMember(Name = "name", Order = 4, EmitDefaultValue = false)]
    public string? Name { get; set; }

    [DataMember(Name = "installed", Order = 5, EmitDefaultValue = false)]
    public string? Installed { get; set; }

    [DataMember(Name = "required", Order = 6, EmitDefaultValue = false)]
    public string? Required { get; set; }

    [DataMember(Name = "url", Order = 7, EmitDefaultValue = false)]
    public string? Url { get; set; }
}

[DataContract]
public sealed class UpscalerBuildEntry
{
    [DataMember(Name = "id", Order = 1, IsRequired = true)]
    public string Id { get; set; } = "";

    [DataMember(Name = "family", Order = 2, IsRequired = true)]
    public string Family { get; set; } = "";

    [DataMember(Name = "version", Order = 3, IsRequired = true)]
    public string Version { get; set; } = "";

    [DataMember(Name = "channel", Order = 4, IsRequired = true)]
    public string Channel { get; set; } = "";

    [DataMember(Name = "download_bytes", Order = 5, IsRequired = true)]
    public long DownloadBytes { get; set; }

    [DataMember(Name = "models", Order = 6, IsRequired = true)]
    public string[] Models { get; set; } = new string[0];

    /// <summary>False when the catalog does not list this GPU: still offered, with a warning, as on Linux.</summary>
    [DataMember(Name = "supported", Order = 7, IsRequired = true)]
    public bool Supported { get; set; }

    /// <summary><c>dll</c> for the DLL mode, which swaps the game's own FidelityFX libraries; absent for OptiScaler.</summary>
    [DataMember(Name = "engine", Order = 8, EmitDefaultValue = false)]
    public string? Engine { get; set; }
}

[DataContract]
public sealed class UpscalerInstallEntry
{
    [DataMember(Name = "build", Order = 1, IsRequired = true)]
    public string Build { get; set; } = "";

    [DataMember(Name = "version", Order = 2, EmitDefaultValue = false)]
    public string? Version { get; set; }

    [DataMember(Name = "proxy", Order = 3, IsRequired = true)]
    public string Proxy { get; set; } = "";

    [DataMember(Name = "exe", Order = 4, EmitDefaultValue = false)]
    public string? Exe { get; set; }

    [DataMember(Name = "quality", Order = 5, EmitDefaultValue = false)]
    public string? Quality { get; set; }

    [DataMember(Name = "model", Order = 6, EmitDefaultValue = false)]
    public string? Model { get; set; }

    [DataMember(Name = "installed_at", Order = 7, IsRequired = true)]
    public long InstalledAt { get; set; }

    /// <summary><c>installed</c> or <c>missing</c>, from the game's own manifest.</summary>
    [DataMember(Name = "status", Order = 8, IsRequired = true)]
    public string Status { get; set; } = UpscalerGameStates.Missing;

    [DataMember(Name = "label", Order = 9, EmitDefaultValue = false)]
    public string? Label { get; set; }

    /// <summary>Panel's arguments in Steam's launch options.</summary>
    [DataMember(Name = "added_args", Order = 10, EmitDefaultValue = false)]
    public string[]? AddedArgs { get; set; }

    /// <summary>Arguments the recipe needs that Panel could not put in Steam (Steam closed or without debugging).</summary>
    [DataMember(Name = "missing_args", Order = 11, EmitDefaultValue = false)]
    public string[]? MissingArgs { get; set; }

    /// <summary>What OptiScaler's log says since the install: <c>not_run</c>, <c>loaded</c> or <c>active</c>.</summary>
    [DataMember(Name = "verdict", Order = 12, EmitDefaultValue = false)]
    public string? Verdict { get; set; }

    /// <summary>The upscaler the log shows running, as OptiScaler names it.</summary>
    [DataMember(Name = "observed", Order = 13, EmitDefaultValue = false)]
    public string? Observed { get; set; }

    /// <summary>The FSR 4 library that answered, with its version and model when the log names them.</summary>
    [DataMember(Name = "provider", Order = 14, EmitDefaultValue = false)]
    public string? Provider { get; set; }

    /// <summary>FSR 4 was chosen but the log shows an older FSR running instead.</summary>
    [DataMember(Name = "fallback", Order = 15, EmitDefaultValue = false)]
    public string? Fallback { get; set; }
}

[DataContract]
public sealed class UpscalerGameDetail
{
    /// <summary>The last installs in this game, newest last, with what the log said about each.</summary>
    [DataMember(Name = "history", Order = 20, EmitDefaultValue = false)]
    public UpscalerHistoryEntry[]? History { get; set; }

    [DataMember(Name = "game", Order = 1, IsRequired = true)]
    public UpscalerGameSummary Game { get; set; } = new();

    [DataMember(Name = "exe", Order = 2, EmitDefaultValue = false)]
    public string? Exe { get; set; }

    [DataMember(Name = "apis", Order = 3, IsRequired = true)]
    public string[] Apis { get; set; } = new string[0];

    [DataMember(Name = "inputs", Order = 4, IsRequired = true)]
    public UpscalerInput[] Inputs { get; set; } = new UpscalerInput[0];

    [DataMember(Name = "anti_cheat", Order = 5, IsRequired = true)]
    public bool AntiCheat { get; set; }

    [DataMember(Name = "foreign", Order = 6, EmitDefaultValue = false)]
    public UpscalerForeignSummary? Foreign { get; set; }

    [DataMember(Name = "recipe", Order = 7, EmitDefaultValue = false)]
    public UpscalerRecipeStatus? Recipe { get; set; }

    [DataMember(Name = "preferred", Order = 8, EmitDefaultValue = false)]
    public string? Preferred { get; set; }

    [DataMember(Name = "builds", Order = 9, IsRequired = true)]
    public UpscalerBuildEntry[] Builds { get; set; } = new UpscalerBuildEntry[0];

    [DataMember(Name = "install", Order = 10, EmitDefaultValue = false)]
    public UpscalerInstallEntry? Install { get; set; }
}

public static class UpscalerJobStates
{
    public const string Running = "running";
    public const string Done = "done";
    public const string Error = "error";
}

[DataContract]
public sealed class UpscalerJobStatus
{
    [DataMember(Name = "id", Order = 1, IsRequired = true)]
    public string Id { get; set; } = "";

    /// <summary><c>install</c> or <c>uninstall</c>.</summary>
    [DataMember(Name = "kind", Order = 2, IsRequired = true)]
    public string Kind { get; set; } = "";

    [DataMember(Name = "appid", Order = 3, IsRequired = true)]
    public string AppId { get; set; } = "";

    [DataMember(Name = "state", Order = 4, IsRequired = true)]
    public string State { get; set; } = UpscalerJobStates.Running;

    /// <summary><c>prepare</c>, <c>download</c>, <c>install</c>, <c>restore</c> or <c>done</c>.</summary>
    [DataMember(Name = "stage", Order = 5, IsRequired = true)]
    public string Stage { get; set; } = "prepare";

    [DataMember(Name = "done_bytes", Order = 6, IsRequired = true)]
    public long DoneBytes { get; set; }

    [DataMember(Name = "total_bytes", Order = 7, IsRequired = true)]
    public long TotalBytes { get; set; }

    [DataMember(Name = "error", Order = 8, EmitDefaultValue = false)]
    public string? Error { get; set; }

    [DataMember(Name = "detail", Order = 9, EmitDefaultValue = false)]
    public string? Detail { get; set; }
}

/// <summary>A game's cover, already downscaled: <see cref="UpscalersWireCodec.MaximumCoverBytes"/> at most, base64 in <see cref="Data"/>.</summary>
[DataContract]
public sealed class UpscalerCover
{
    public const string Jpeg = "image/jpeg";
    public const string Png = "image/png";

    [DataMember(Name = "mime", Order = 1, IsRequired = true)]
    public string Mime { get; set; } = Jpeg;

    [DataMember(Name = "data", Order = 2, IsRequired = true)]
    public string Data { get; set; } = "";
}

[DataContract]
public sealed class UpscalersResponse
{
    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public UpscalersResponseStatus Status { get; set; }

    [DataMember(Name = "error_code", Order = 2, EmitDefaultValue = false)]
    public string? ErrorCode { get; set; }

    [DataMember(Name = "overview", Order = 3, EmitDefaultValue = false)]
    public UpscalersOverview? Overview { get; set; }

    [DataMember(Name = "game", Order = 4, EmitDefaultValue = false)]
    public UpscalerGameDetail? Game { get; set; }

    [DataMember(Name = "job", Order = 5, EmitDefaultValue = false)]
    public UpscalerJobStatus? Job { get; set; }

    [DataMember(Name = "cover", Order = 6, EmitDefaultValue = false)]
    public UpscalerCover? Cover { get; set; }

    [DataMember(Name = "ingame", Order = 7, EmitDefaultValue = false)]
    public string? InGame { get; set; }

    public static UpscalersResponse Rejected(string errorCode, UpscalerJobStatus? job = null) =>
        new() { Status = UpscalersResponseStatus.Rejected, ErrorCode = errorCode, Job = job };

    public static UpscalersResponse Fault(string errorCode, UpscalerJobStatus? job = null) =>
        new() { Status = UpscalersResponseStatus.Fault, ErrorCode = errorCode, Job = job };

    internal void Validate()
    {
        var valid = (Status == UpscalersResponseStatus.Ok) == (ErrorCode is null)
            && (Overview is null || Overview.Games is not null && Overview.Games.Select(game => game.AppId).Distinct().Count() == Overview.Games.Length)
            && (InGame is null || InGameModes.IsValid(InGame))
            && (Cover is null || Cover.Mime is UpscalerCover.Jpeg or UpscalerCover.Png && Cover.Data is { Length: > 0 and <= UpscalersWireCodec.MaximumCoverBytes / 3 * 4 + 4 });
        if (!valid)
        {
            throw new InvalidDataException("Upscalers response is invalid.");
        }
    }
}

public static class UpscalersWireCodec
{
    public const int MaximumRequestLength = 1024;
    public const int MaximumResponseLength = 512 * 1024;
    public const int MaximumCoverBytes = 256 * 1024;
    public const int MaximumCoverWidth = 200;

    private static readonly DataContractJsonSerializer RequestSerializer = new(typeof(UpscalersRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer = new(typeof(UpscalersResponse));

    public static string SerializeRequest(UpscalersRequest request)
    {
        request.Validate();
        return Write(RequestSerializer, request);
    }

    public static UpscalersRequest DeserializeRequest(string payload)
    {
        var request = Read(RequestSerializer, payload) as UpscalersRequest
            ?? throw new InvalidDataException("Payload did not contain an upscalers request.");
        request.Validate();
        return request;
    }

    public static string SerializeResponse(UpscalersResponse response)
    {
        response.Validate();
        var text = Write(ResponseSerializer, response);
        if (Encoding.UTF8.GetByteCount(text) > MaximumResponseLength)
        {
            throw new InvalidDataException("Upscalers response is too large.");
        }

        return text;
    }

    public static UpscalersResponse DeserializeResponse(string payload)
    {
        var response = Read(ResponseSerializer, payload) as UpscalersResponse
            ?? throw new InvalidDataException("Payload did not contain an upscalers response.");
        response.Validate();
        return response;
    }

    private static string Write(DataContractJsonSerializer serializer, object value)
    {
        using var stream = new MemoryStream();
        serializer.WriteObject(stream, value);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static object? Read(DataContractJsonSerializer serializer, string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        return serializer.ReadObject(stream);
    }
}
