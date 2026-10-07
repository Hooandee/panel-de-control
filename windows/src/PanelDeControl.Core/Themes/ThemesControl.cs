using System.Collections.Generic;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Themes;

[DataContract]
public enum ThemesOperation
{
    [EnumMember(Value = "get")]
    Get = 0,

    [EnumMember(Value = "refresh_catalog")]
    RefreshCatalog = 1,

    [EnumMember(Value = "install")]
    Install = 2,

    [EnumMember(Value = "set_enabled")]
    SetEnabled = 3,

    [EnumMember(Value = "set_option")]
    SetOption = 4,

    [EnumMember(Value = "enable_steam_debugging")]
    EnableSteamDebugging = 5,

    [EnumMember(Value = "restart_steam")]
    RestartSteam = 6,
}

/// <summary>Why themes can or cannot reach Steam, as the widget explains it.</summary>
[DataContract]
public enum ThemesConnection
{
    [EnumMember(Value = "steam_not_installed")]
    SteamNotInstalled = 0,

    [EnumMember(Value = "debugging_off")]
    DebuggingOff = 1,

    [EnumMember(Value = "steam_not_running")]
    SteamNotRunning = 2,

    [EnumMember(Value = "restart_required")]
    RestartRequired = 3,

    [EnumMember(Value = "waiting_for_big_picture")]
    WaitingForBigPicture = 4,

    [EnumMember(Value = "connected")]
    Connected = 5,
}

[DataContract]
public enum ThemesResponseStatus
{
    [EnumMember(Value = "ok")]
    Ok = 0,

    [EnumMember(Value = "rejected")]
    Rejected = 1,

    [EnumMember(Value = "fault")]
    Fault = 2,
}

[DataContract]
public sealed class ThemesRequest
{
    public const int MaximumFieldLength = 128;

    private ThemesRequest()
    {
    }

    private ThemesRequest(ThemesOperation operation, string? catalogId = null, string? version = null, string? name = null, bool? enabled = null, string? option = null, string? value = null)
    {
        Operation = operation;
        CatalogId = catalogId;
        Version = version;
        Name = name;
        Enabled = enabled;
        Option = option;
        Value = value;
    }

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public ThemesOperation Operation { get; private set; }

    [DataMember(Name = "catalog_id", Order = 2, EmitDefaultValue = false)]
    public string? CatalogId { get; private set; }

    [DataMember(Name = "version", Order = 3, EmitDefaultValue = false)]
    public string? Version { get; private set; }

    [DataMember(Name = "name", Order = 4, EmitDefaultValue = false)]
    public string? Name { get; private set; }

    [DataMember(Name = "enabled", Order = 5, EmitDefaultValue = false)]
    public bool? Enabled { get; private set; }

    [DataMember(Name = "option", Order = 6, EmitDefaultValue = false)]
    public string? Option { get; private set; }

    [DataMember(Name = "value", Order = 7, EmitDefaultValue = false)]
    public string? Value { get; private set; }

    public static ThemesRequest Get() => new(ThemesOperation.Get);

    public static ThemesRequest RefreshCatalog() => new(ThemesOperation.RefreshCatalog);

    public static ThemesRequest Install(string catalogId, string version) => new(ThemesOperation.Install, catalogId: catalogId, version: version);

    public static ThemesRequest SetEnabled(string name, bool enabled) => new(ThemesOperation.SetEnabled, name: name, enabled: enabled);

    public static ThemesRequest SetOption(string name, string option, string value) => new(ThemesOperation.SetOption, name: name, option: option, value: value);

    public static ThemesRequest EnableSteamDebugging() => new(ThemesOperation.EnableSteamDebugging);

    public static ThemesRequest RestartSteam() => new(ThemesOperation.RestartSteam);

    internal void Validate()
    {
        bool Present(string? field) => !string.IsNullOrWhiteSpace(field) && field!.Length <= MaximumFieldLength;
        bool Absent(string? field) => field is null;
        var valid = Operation switch
        {
            ThemesOperation.Get or ThemesOperation.RefreshCatalog or ThemesOperation.EnableSteamDebugging or ThemesOperation.RestartSteam =>
                Absent(CatalogId) && Absent(Version) && Absent(Name) && Enabled is null && Absent(Option) && Absent(Value),
            ThemesOperation.Install => Present(CatalogId) && Present(Version) && Absent(Name) && Enabled is null && Absent(Option) && Absent(Value),
            ThemesOperation.SetEnabled => Present(Name) && Enabled is not null && Absent(CatalogId) && Absent(Version) && Absent(Option) && Absent(Value),
            ThemesOperation.SetOption => Present(Name) && Present(Option) && Present(Value) && Absent(CatalogId) && Absent(Version) && Enabled is null,
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("Themes request is invalid.");
        }
    }
}

[DataContract]
public sealed class LocalizedText
{
    public LocalizedText(string language, string text)
    {
        Language = language;
        Text = text;
    }

    [DataMember(Name = "lang", Order = 1, IsRequired = true)]
    public string Language { get; private set; }

    [DataMember(Name = "text", Order = 2, IsRequired = true)]
    public string Text { get; private set; }

    /// <summary>The text for a UI language: exact tag, then its base language, then English.</summary>
    public static string? Pick(IReadOnlyList<LocalizedText>? texts, string language)
    {
        if (texts is null || texts.Count == 0)
        {
            return null;
        }

        var baseLanguage = language.Split('-')[0];
        return texts.FirstOrDefault(text => string.Equals(text.Language, language, System.StringComparison.OrdinalIgnoreCase))?.Text
            ?? texts.FirstOrDefault(text => string.Equals(text.Language.Split('-')[0], baseLanguage, System.StringComparison.OrdinalIgnoreCase))?.Text
            ?? texts.FirstOrDefault(text => text.Language == "en")?.Text
            ?? texts[0].Text;
    }
}

[DataContract]
public sealed class ThemeOptionValue
{
    public ThemeOptionValue(string value, IReadOnlyList<LocalizedText> label)
    {
        Value = value;
        Label = label.ToArray();
    }

    [DataMember(Name = "value", Order = 1, IsRequired = true)]
    public string Value { get; private set; }

    [DataMember(Name = "label", Order = 2, EmitDefaultValue = false)]
    public LocalizedText[] Label { get; private set; }
}

[DataContract]
public sealed class ThemeOption
{
    public ThemeOption(string name, IReadOnlyList<LocalizedText> label, string type, string value, string defaultValue, IReadOnlyList<ThemeOptionValue> values)
    {
        Name = name;
        Label = label.ToArray();
        Type = type;
        Value = value;
        DefaultValue = defaultValue;
        Values = values.ToArray();
    }

    [DataMember(Name = "name", Order = 1, IsRequired = true)]
    public string Name { get; private set; }

    [DataMember(Name = "label", Order = 2, EmitDefaultValue = false)]
    public LocalizedText[] Label { get; private set; }

    /// <summary><c>dropdown</c>, <c>checkbox</c>, <c>slider</c> or <c>none</c> (a section title).</summary>
    [DataMember(Name = "type", Order = 3, IsRequired = true)]
    public string Type { get; private set; }

    [DataMember(Name = "value", Order = 4, IsRequired = true)]
    public string Value { get; private set; }

    [DataMember(Name = "default", Order = 5, IsRequired = true)]
    public string DefaultValue { get; private set; }

    [DataMember(Name = "values", Order = 6, IsRequired = true)]
    public ThemeOptionValue[] Values { get; private set; }
}

[DataContract]
public sealed class ThemeEntry
{
    [DataMember(Name = "catalog_id", Order = 1, EmitDefaultValue = false)]
    public string? CatalogId { get; set; }

    [DataMember(Name = "name", Order = 2, IsRequired = true)]
    public string Name { get; set; } = string.Empty;

    [DataMember(Name = "display_name", Order = 3, EmitDefaultValue = false)]
    public LocalizedText[]? DisplayName { get; set; }

    [DataMember(Name = "description", Order = 4, EmitDefaultValue = false)]
    public LocalizedText[]? Description { get; set; }

    [DataMember(Name = "installed_version", Order = 5, EmitDefaultValue = false)]
    public string? InstalledVersion { get; set; }

    [DataMember(Name = "published_version", Order = 6, EmitDefaultValue = false)]
    public string? PublishedVersion { get; set; }

    [DataMember(Name = "enabled", Order = 7)]
    public bool Enabled { get; set; }

    [DataMember(Name = "broken", Order = 8, EmitDefaultValue = false)]
    public string? Broken { get; set; }

    [DataMember(Name = "pages_expected", Order = 9)]
    public int PagesExpected { get; set; }

    [DataMember(Name = "pages_applied", Order = 10)]
    public int PagesApplied { get; set; }

    [DataMember(Name = "runtime_expected", Order = 11)]
    public bool RuntimeExpected { get; set; }

    [DataMember(Name = "runtime_mounted", Order = 12)]
    public bool RuntimeMounted { get; set; }

    [DataMember(Name = "options", Order = 13, EmitDefaultValue = false)]
    public ThemeOption[]? Options { get; set; }

    public bool Installed => InstalledVersion is not null;

    public bool UpdateAvailable =>
        InstalledVersion is not null && PublishedVersion is not null && Broken is null && CompareVersions(PublishedVersion, InstalledVersion) > 0;

    /// <summary>Applied means every targeted Steam page read back complete and the runtime mounted.</summary>
    public bool Applied =>
        Enabled && PagesExpected > 0 && PagesApplied == PagesExpected && (!RuntimeExpected || RuntimeMounted);

    private static int CompareVersions(string left, string right)
    {
        var a = left.Split('.');
        var b = right.Split('.');
        for (var index = 0; index < 3 && index < a.Length && index < b.Length; index++)
        {
            if (int.TryParse(a[index], out var x) && int.TryParse(b[index], out var y) && x != y)
            {
                return x.CompareTo(y);
            }
        }

        return 0;
    }
}

[DataContract]
public sealed class ThemesResponse
{
    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ThemesResponseStatus Status { get; set; }

    [DataMember(Name = "error_code", Order = 2, EmitDefaultValue = false)]
    public string? ErrorCode { get; set; }

    [DataMember(Name = "connection", Order = 3, IsRequired = true)]
    public ThemesConnection Connection { get; set; }

    [DataMember(Name = "catalog_error", Order = 4, EmitDefaultValue = false)]
    public string? CatalogError { get; set; }

    [DataMember(Name = "themes", Order = 5, IsRequired = true)]
    public ThemeEntry[] Themes { get; set; } = new ThemeEntry[0];

    [DataMember(Name = "runtime_errors", Order = 6, EmitDefaultValue = false)]
    public string[]? RuntimeErrors { get; set; }

    internal void Validate()
    {
        var valid = (Status == ThemesResponseStatus.Ok) == (ErrorCode is null)
            && Themes is not null
            && Themes.All(theme => !string.IsNullOrWhiteSpace(theme.Name))
            && Themes.Select(theme => theme.Name).Distinct().Count() == Themes.Length;
        if (!valid)
        {
            throw new InvalidDataException("Themes response is invalid.");
        }
    }
}

public static class ThemesWireCodec
{
    public const int MaximumRequestLength = 1024;
    public const int MaximumResponseLength = 512 * 1024;

    private static readonly DataContractJsonSerializer RequestSerializer = new(typeof(ThemesRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer = new(typeof(ThemesResponse));

    public static string SerializeRequest(ThemesRequest request)
    {
        request.Validate();
        return Write(RequestSerializer, request);
    }

    public static ThemesRequest DeserializeRequest(string payload)
    {
        var request = Read(RequestSerializer, payload) as ThemesRequest
            ?? throw new InvalidDataException("Payload did not contain a themes request.");
        request.Validate();
        return request;
    }

    public static string SerializeResponse(ThemesResponse response)
    {
        response.Validate();
        return Write(ResponseSerializer, response);
    }

    public static ThemesResponse DeserializeResponse(string payload)
    {
        var response = Read(ResponseSerializer, payload) as ThemesResponse
            ?? throw new InvalidDataException("Payload did not contain a themes response.");
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
            throw new System.ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        return serializer.ReadObject(stream);
    }
}
