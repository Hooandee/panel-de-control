using System.Runtime.Serialization;

namespace PanelDeControl.Core.Controls;

[DataContract]
public enum ControlStatus
{
    [EnumMember]
    Available = 0,

    [EnumMember]
    Applied = 1,

    [EnumMember]
    Unavailable = 2,

    [EnumMember]
    PermissionRequired = 3,

    [EnumMember]
    Rejected = 4,

    [EnumMember]
    Unverifiable = 5,

    [EnumMember]
    Fault = 6,
}
