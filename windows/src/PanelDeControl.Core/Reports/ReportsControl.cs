using System;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Reports;

[DataContract]
public enum ReportKind
{
    [EnumMember(Value = "bug")]
    Bug = 0,

    [EnumMember(Value = "feature")]
    Feature = 1,
}

[DataContract]
public enum ReportStatus
{
    [EnumMember(Value = "sent")]
    Sent = 0,

    [EnumMember(Value = "saved")]
    Saved = 1,

    [EnumMember(Value = "rejected")]
    Rejected = 2,
}

/// <summary>
/// What the widget asks the companion to send: the user's own words plus the areas they picked.
/// The companion adds every technical detail itself.
/// </summary>
[DataContract]
public sealed class ReportRequest
{
    public const int MaximumTextLength = 4000;

    /// <summary>Areas a Windows report can be about while Windows support is in preview.</summary>
    public static readonly string[] AvailableCategories = { "themes" };

    private ReportRequest()
    {
    }

    public ReportRequest(ReportKind kind, string[] categories, string text)
    {
        Kind = kind;
        Categories = categories;
        Text = text;
    }

    [DataMember(Name = "kind", Order = 1, IsRequired = true)]
    public ReportKind Kind { get; private set; }

    [DataMember(Name = "categories", Order = 2, IsRequired = true)]
    public string[] Categories { get; private set; } = Array.Empty<string>();

    [DataMember(Name = "text", Order = 3, IsRequired = true)]
    public string Text { get; private set; } = string.Empty;

    public void Validate()
    {
        if (!Enum.IsDefined(typeof(ReportKind), Kind))
        {
            throw new InvalidDataException("report_kind_invalid");
        }

        if (Categories is null ||
            Categories.Length == 0 ||
            Categories.Length > AvailableCategories.Length ||
            Categories.Distinct(StringComparer.Ordinal).Count() != Categories.Length ||
            Categories.Any(category => !AvailableCategories.Contains(category)))
        {
            throw new InvalidDataException("report_categories_invalid");
        }

        if (string.IsNullOrWhiteSpace(Text))
        {
            throw new InvalidDataException("report_text_required");
        }

        if (Text.Length > MaximumTextLength)
        {
            throw new InvalidDataException("report_text_too_long");
        }
    }
}

[DataContract]
public sealed class ReportResponse
{
    private ReportResponse()
    {
    }

    private ReportResponse(ReportStatus status, string? code, string? issueUrl, string? savedPath, string? errorCode)
    {
        Status = status;
        Code = code;
        IssueUrl = issueUrl;
        SavedPath = savedPath;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ReportStatus Status { get; private set; }

    [DataMember(Name = "code", Order = 2, EmitDefaultValue = false)]
    public string? Code { get; private set; }

    [DataMember(Name = "issue_url", Order = 3, EmitDefaultValue = false)]
    public string? IssueUrl { get; private set; }

    [DataMember(Name = "saved_path", Order = 4, EmitDefaultValue = false)]
    public string? SavedPath { get; private set; }

    [DataMember(Name = "error_code", Order = 5, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static ReportResponse Sent(string code, string? issueUrl) =>
        new(ReportStatus.Sent, code, issueUrl, null, null);

    /// <summary>The service could not be reached; the bundle stayed on disk so it can be sent by hand.</summary>
    public static ReportResponse Saved(string? savedPath, string errorCode) =>
        new(ReportStatus.Saved, null, null, savedPath, errorCode);

    public static ReportResponse Rejected(string errorCode) =>
        new(ReportStatus.Rejected, null, null, null, errorCode);

    public void Validate()
    {
        switch (Status)
        {
            case ReportStatus.Sent when string.IsNullOrWhiteSpace(Code):
                throw new InvalidDataException("A sent report needs its code.");
            case ReportStatus.Saved or ReportStatus.Rejected when string.IsNullOrWhiteSpace(ErrorCode):
                throw new InvalidDataException("A report that was not sent needs its error code.");
            case ReportStatus.Sent or ReportStatus.Saved or ReportStatus.Rejected:
                return;
            default:
                throw new InvalidDataException("Unknown report status.");
        }
    }
}

public static class ReportWireCodec
{
    public const int MaximumRequestLength = 64 * 1024;
    public const int MaximumResponseLength = 8 * 1024;

    private static readonly DataContractJsonSerializer RequestSerializer = new(typeof(ReportRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer = new(typeof(ReportResponse));

    public static string SerializeRequest(ReportRequest request)
    {
        request.Validate();
        return Write(RequestSerializer, request);
    }

    public static ReportRequest DeserializeRequest(string payload)
    {
        var request = Read(RequestSerializer, payload) as ReportRequest
            ?? throw new InvalidDataException("Payload did not contain a report request.");
        request.Validate();
        return request;
    }

    public static string SerializeResponse(ReportResponse response)
    {
        response.Validate();
        return Write(ResponseSerializer, response);
    }

    public static ReportResponse DeserializeResponse(string payload)
    {
        var response = Read(ResponseSerializer, payload) as ReportResponse
            ?? throw new InvalidDataException("Payload did not contain a report response.");
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
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        return serializer.ReadObject(stream);
    }
}
