using System.Runtime.Serialization;

namespace PanelDeControl.Core.Telemetry;

[DataContract]
public enum ReadingStatus
{
    [EnumMember]
    Available = 0,

    [EnumMember]
    Unavailable = 1,

    [EnumMember]
    PermissionRequired = 2,

    [EnumMember]
    Fault = 3,
}
