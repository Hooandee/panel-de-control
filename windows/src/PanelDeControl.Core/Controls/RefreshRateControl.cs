using System.Collections.Generic;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum RefreshRateOperation
{
    [EnumMember]
    Get = 0,

    [EnumMember]
    Set = 1,
}

[DataContract]
public sealed class RefreshRateRequest
{
    public const int MinimumHertz = 24;
    public const int MaximumHertz = 500;

    private RefreshRateRequest()
    {
    }

    private RefreshRateRequest(RefreshRateOperation operation, int? requestedHertz)
    {
        Operation = operation;
        RequestedHertz = requestedHertz;
    }

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public RefreshRateOperation Operation { get; private set; }

    [DataMember(Name = "requested_hz", Order = 2, EmitDefaultValue = false)]
    public int? RequestedHertz { get; private set; }

    public static RefreshRateRequest Get() => new(RefreshRateOperation.Get, null);

    public static RefreshRateRequest Set(int requestedHertz)
    {
        if (!IsPlausible(requestedHertz))
        {
            throw new ArgumentOutOfRangeException(nameof(requestedHertz));
        }

        return new RefreshRateRequest(RefreshRateOperation.Set, requestedHertz);
    }

    public static bool IsPlausible(int hertz) => hertz >= MinimumHertz && hertz <= MaximumHertz;

    internal void Validate()
    {
        var valid = Operation switch
        {
            RefreshRateOperation.Get => !RequestedHertz.HasValue,
            RefreshRateOperation.Set => RequestedHertz is int hertz && IsPlausible(hertz),
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("Refresh rate request is invalid.");
        }
    }
}

[DataContract]
public sealed class RefreshRateResponse
{
    private RefreshRateResponse()
    {
    }

    private RefreshRateResponse(
        ControlStatus status,
        int? requestedHertz,
        int? observedHertz,
        IEnumerable<int>? supportedHertz,
        string? errorCode)
    {
        Status = status;
        RequestedHertz = requestedHertz;
        ObservedHertz = observedHertz;
        SupportedHertz = supportedHertz?.Distinct().OrderBy(hertz => hertz).ToArray();
        ErrorCode = errorCode;
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ControlStatus Status { get; private set; }

    [DataMember(Name = "requested_hz", Order = 2, EmitDefaultValue = false)]
    public int? RequestedHertz { get; private set; }

    [DataMember(Name = "observed_hz", Order = 3, EmitDefaultValue = false)]
    public int? ObservedHertz { get; private set; }

    [DataMember(Name = "supported_hz", Order = 4, EmitDefaultValue = false)]
    public int[]? SupportedHertz { get; private set; }

    [DataMember(Name = "error_code", Order = 5, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public IReadOnlyList<int> Supported => SupportedHertz ?? Array.Empty<int>();

    public static RefreshRateResponse Available(int observedHertz, IEnumerable<int> supportedHertz) =>
        new(ControlStatus.Available, null, observedHertz, supportedHertz, null);

    public static RefreshRateResponse Applied(int requestedHertz, int observedHertz, IEnumerable<int> supportedHertz) =>
        new(ControlStatus.Applied, requestedHertz, observedHertz, supportedHertz, null);

    public static RefreshRateResponse Unverifiable(int requestedHertz, int? observedHertz, IEnumerable<int>? supportedHertz, string errorCode) =>
        new(ControlStatus.Unverifiable, requestedHertz, observedHertz, supportedHertz, errorCode);

    public static RefreshRateResponse Rejected(string errorCode, IEnumerable<int>? supportedHertz = null, int? observedHertz = null) =>
        new(ControlStatus.Rejected, null, observedHertz, supportedHertz, errorCode);

    public static RefreshRateResponse Unavailable(string errorCode) =>
        new(ControlStatus.Unavailable, null, null, null, errorCode);

    public static RefreshRateResponse Fault(string errorCode) =>
        new(ControlStatus.Fault, null, null, null, errorCode);

    internal void Validate()
    {
        var plausible = (ObservedHertz is null || RefreshRateRequest.IsPlausible(ObservedHertz.Value)) &&
            (RequestedHertz is null || RefreshRateRequest.IsPlausible(RequestedHertz.Value)) &&
            Supported.All(RefreshRateRequest.IsPlausible);
        var valid = plausible && Status switch
        {
            ControlStatus.Available => ObservedHertz.HasValue && RequestedHertz is null && ErrorCode is null,
            ControlStatus.Applied => ObservedHertz.HasValue && RequestedHertz == ObservedHertz && ErrorCode is null,
            ControlStatus.Unverifiable => RequestedHertz.HasValue && !string.IsNullOrWhiteSpace(ErrorCode),
            ControlStatus.Rejected or ControlStatus.Unavailable or ControlStatus.Fault =>
                RequestedHertz is null && !string.IsNullOrWhiteSpace(ErrorCode),
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("Refresh rate response is invalid.");
        }
    }
}

public static class RefreshRateWireCodec
{
    private static readonly DataContractJsonSerializer RequestSerializer = new(typeof(RefreshRateRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer = new(typeof(RefreshRateResponse));

    public static string SerializeRequest(RefreshRateRequest request)
    {
        request.Validate();
        return Write(RequestSerializer, request);
    }

    public static RefreshRateRequest DeserializeRequest(string payload)
    {
        var request = Read(RequestSerializer, payload) as RefreshRateRequest
            ?? throw new InvalidDataException("Payload did not contain a refresh rate request.");
        request.Validate();
        return request;
    }

    public static string SerializeResponse(RefreshRateResponse response)
    {
        response.Validate();
        return Write(ResponseSerializer, response);
    }

    public static RefreshRateResponse DeserializeResponse(string payload)
    {
        var response = Read(ResponseSerializer, payload) as RefreshRateResponse
            ?? throw new InvalidDataException("Payload did not contain a refresh rate response.");
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
