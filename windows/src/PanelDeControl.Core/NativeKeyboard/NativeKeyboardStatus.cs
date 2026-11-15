using System.Runtime.Serialization;

namespace PanelDeControl.Core.NativeKeyboard;

[DataContract]
public sealed class NativeKeyboardStatus
{
    [DataMember(Name = "requested", Order = 1)]
    public bool Requested { get; set; }
    [DataMember(Name = "status", Order = 2)]
    public string Status { get; set; } = "disabled";
    [DataMember(Name = "error_code", Order = 3, EmitDefaultValue = false)]
    public string? ErrorCode { get; set; }
    [DataMember(Name = "connected", Order = 4)]
    public bool Connected { get; set; }
    [DataMember(Name = "windows_build", Order = 5)]
    public int WindowsBuild { get; set; }
    [DataMember(Name = "architecture", Order = 6)]
    public string Architecture { get; set; } = "unknown";
    [DataMember(Name = "process_id", Order = 7)]
    public int ProcessId { get; set; }
    [DataMember(Name = "observed_elements", Order = 8)]
    public int ObservedElements { get; set; }
    [DataMember(Name = "styled_keys", Order = 10)]
    public int StyledKeys { get; set; }
    [DataMember(Name = "restored_keys", Order = 11)]
    public int RestoredKeys { get; set; }
    [DataMember(Name = "key_count", Order = 12)]
    public int KeyCount { get; set; }
    [DataMember(Name = "pending_keys", Order = 14)]
    public int PendingKeys { get; set; }
    [DataMember(Name = "hresult", Order = 13)]
    public int HResult { get; set; }
    [DataMember(Name = "diagnostics", Order = 9, EmitDefaultValue = false)]
    public string? Diagnostics { get; set; }
}
