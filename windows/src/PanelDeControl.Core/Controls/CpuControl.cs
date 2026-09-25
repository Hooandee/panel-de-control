using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum CpuControlOperation
{
    [EnumMember]
    Get = 0,

    [EnumMember]
    SetBoost = 1,

    [EnumMember]
    SetMaximumState = 2,
}

[DataContract]
public sealed class CpuControlRequest
{
    public const int LowestStatePercent = 5;
    public const int HighestStatePercent = 100;

    private CpuControlRequest()
    {
    }

    private CpuControlRequest(CpuControlOperation operation, bool? boostEnabled, int? maximumStatePercent)
    {
        Operation = operation;
        BoostEnabled = boostEnabled;
        MaximumStatePercent = maximumStatePercent;
    }

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public CpuControlOperation Operation { get; private set; }

    [DataMember(Name = "boost_enabled", Order = 2, EmitDefaultValue = false)]
    public bool? BoostEnabled { get; private set; }

    [DataMember(Name = "maximum_state_percent", Order = 3, EmitDefaultValue = false)]
    public int? MaximumStatePercent { get; private set; }

    public static CpuControlRequest Get() => new(CpuControlOperation.Get, null, null);

    public static CpuControlRequest SetBoost(bool enabled) => new(CpuControlOperation.SetBoost, enabled, null);

    public static CpuControlRequest SetMaximumState(int percent)
    {
        if (!IsState(percent))
        {
            throw new ArgumentOutOfRangeException(nameof(percent));
        }

        return new CpuControlRequest(CpuControlOperation.SetMaximumState, null, percent);
    }

    public static bool IsState(int percent) => percent >= LowestStatePercent && percent <= HighestStatePercent;

    internal void Validate()
    {
        var valid = Operation switch
        {
            CpuControlOperation.Get => !BoostEnabled.HasValue && !MaximumStatePercent.HasValue,
            CpuControlOperation.SetBoost => BoostEnabled.HasValue && !MaximumStatePercent.HasValue,
            CpuControlOperation.SetMaximumState => !BoostEnabled.HasValue &&
                MaximumStatePercent is int percent && IsState(percent),
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("CPU control request is invalid.");
        }
    }
}

[DataContract]
public sealed class CpuControlResponse
{
    private CpuControlResponse()
    {
    }

    private CpuControlResponse(ControlStatus status, bool? boostEnabled, int? maximumStatePercent, string? errorCode)
    {
        Status = status;
        BoostEnabled = boostEnabled;
        MaximumStatePercent = maximumStatePercent;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public ControlStatus Status { get; private set; }

    [DataMember(Name = "boost_enabled", Order = 2, EmitDefaultValue = false)]
    public bool? BoostEnabled { get; private set; }

    [DataMember(Name = "maximum_state_percent", Order = 3, EmitDefaultValue = false)]
    public int? MaximumStatePercent { get; private set; }

    [DataMember(Name = "error_code", Order = 4, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static CpuControlResponse Available(bool boostEnabled, int maximumStatePercent) =>
        new(ControlStatus.Available, boostEnabled, maximumStatePercent, null);

    public static CpuControlResponse Applied(bool boostEnabled, int maximumStatePercent) =>
        new(ControlStatus.Applied, boostEnabled, maximumStatePercent, null);

    public static CpuControlResponse Unverifiable(bool? boostEnabled, int? maximumStatePercent, string errorCode) =>
        new(ControlStatus.Unverifiable, boostEnabled, maximumStatePercent, errorCode);

    public static CpuControlResponse PermissionRequired(string errorCode) =>
        new(ControlStatus.PermissionRequired, null, null, errorCode);

    public static CpuControlResponse Rejected(string errorCode) =>
        new(ControlStatus.Rejected, null, null, errorCode);

    public static CpuControlResponse Unavailable(string errorCode) =>
        new(ControlStatus.Unavailable, null, null, errorCode);

    public static CpuControlResponse Fault(string errorCode) =>
        new(ControlStatus.Fault, null, null, errorCode);

    internal void Validate()
    {
        var stateValid = MaximumStatePercent is null || CpuControlRequest.IsState(MaximumStatePercent.Value);
        var valid = stateValid && Status switch
        {
            ControlStatus.Available or ControlStatus.Applied =>
                BoostEnabled.HasValue && MaximumStatePercent.HasValue && ErrorCode is null,
            ControlStatus.Unverifiable => !string.IsNullOrWhiteSpace(ErrorCode),
            ControlStatus.PermissionRequired or ControlStatus.Rejected or ControlStatus.Unavailable or ControlStatus.Fault =>
                !BoostEnabled.HasValue && !MaximumStatePercent.HasValue && !string.IsNullOrWhiteSpace(ErrorCode),
            _ => false,
        };
        if (!valid)
        {
            throw new InvalidDataException("CPU control response is invalid.");
        }
    }
}

public static class CpuControlWireCodec
{
    private static readonly DataContractJsonSerializer RequestSerializer = new(typeof(CpuControlRequest));
    private static readonly DataContractJsonSerializer ResponseSerializer = new(typeof(CpuControlResponse));

    public static string SerializeRequest(CpuControlRequest request)
    {
        request.Validate();
        return Write(RequestSerializer, request);
    }

    public static CpuControlRequest DeserializeRequest(string payload)
    {
        var request = Read(RequestSerializer, payload) as CpuControlRequest
            ?? throw new InvalidDataException("Payload did not contain a CPU control request.");
        request.Validate();
        return request;
    }

    public static string SerializeResponse(CpuControlResponse response)
    {
        response.Validate();
        return Write(ResponseSerializer, response);
    }

    public static CpuControlResponse DeserializeResponse(string payload)
    {
        var response = Read(ResponseSerializer, payload) as CpuControlResponse
            ?? throw new InvalidDataException("Payload did not contain a CPU control response.");
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
