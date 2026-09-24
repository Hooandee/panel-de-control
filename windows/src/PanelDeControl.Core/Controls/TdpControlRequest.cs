using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum TdpControlOperation
{
    [EnumMember]
    Get = 0,

    [EnumMember]
    EnableExperimental = 1,

    [EnumMember]
    DisableExperimental = 2,

    [EnumMember]
    Set = 3,
}

[DataContract]
public sealed class TdpControlRequest
{
    private TdpControlRequest()
    {
    }

    private TdpControlRequest(
        TdpControlOperation operation,
        int? requestedWatts)
    {
        Operation = operation;
        RequestedWatts = requestedWatts;
    }

    [DataMember(Name = "operation", Order = 1, IsRequired = true)]
    public TdpControlOperation Operation { get; private set; }

    [DataMember(Name = "requested_watts", Order = 2, EmitDefaultValue = false)]
    public int? RequestedWatts { get; private set; }

    public static TdpControlRequest Get()
    {
        return new TdpControlRequest(TdpControlOperation.Get, null);
    }

    public static TdpControlRequest EnableExperimental()
    {
        return new TdpControlRequest(
            TdpControlOperation.EnableExperimental,
            null);
    }

    public static TdpControlRequest DisableExperimental()
    {
        return new TdpControlRequest(
            TdpControlOperation.DisableExperimental,
            null);
    }

    public static TdpControlRequest Set(int requestedWatts)
    {
        if (requestedWatts < 0 || requestedWatts > 999)
        {
            throw new ArgumentOutOfRangeException(nameof(requestedWatts));
        }

        return new TdpControlRequest(TdpControlOperation.Set, requestedWatts);
    }

    internal void Validate()
    {
        if (!Enum.IsDefined(typeof(TdpControlOperation), Operation))
        {
            throw new InvalidDataException("TDP operation is invalid.");
        }

        if (Operation == TdpControlOperation.Set)
        {
            if (!RequestedWatts.HasValue ||
                RequestedWatts.Value < 0 ||
                RequestedWatts.Value > 999)
            {
                throw new InvalidDataException(
                    "A TDP set request requires integer watts from zero to 999.");
            }

            return;
        }

        if (RequestedWatts.HasValue)
        {
            throw new InvalidDataException(
                "Only a TDP set request can include requested watts.");
        }
    }
}
