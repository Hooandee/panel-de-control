using System.Globalization;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Capabilities;

[DataContract]
public enum CapabilityStatus
{
    [EnumMember]
    Present = 0,

    [EnumMember]
    Absent = 1,

    [EnumMember]
    PermissionRequired = 2,

    [EnumMember]
    Fault = 3,
}

[DataContract]
public sealed class CapabilityEntry
{
    private CapabilityEntry()
    {
    }

    public CapabilityEntry(string id, CapabilityStatus status, string? errorCode = null)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            throw new ArgumentException("Capability id must not be empty.", nameof(id));
        }

        Id = id;
        Status = status;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "id", Order = 1)]
    public string Id { get; private set; } = string.Empty;

    [DataMember(Name = "status", Order = 2)]
    public CapabilityStatus Status { get; private set; }

    [DataMember(Name = "error_code", Order = 3, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }
}

[DataContract]
public sealed class CapabilityInventory
{
    private CapabilityEntry[] entries = Array.Empty<CapabilityEntry>();

    private CapabilityInventory()
    {
    }

    public CapabilityInventory(
        DateTimeOffset capturedAtUtc,
        string deviceKey,
        IEnumerable<CapabilityEntry> entries)
    {
        CapturedAtUtc = capturedAtUtc.ToUniversalTime();
        DeviceKey = string.IsNullOrWhiteSpace(deviceKey) ? "unknown" : deviceKey;
        this.entries = entries?.ToArray() ?? throw new ArgumentNullException(nameof(entries));
    }

    public DateTimeOffset CapturedAtUtc { get; private set; }

    [DataMember(Name = "captured_at_utc", Order = 1)]
    private string CapturedAtWire
    {
        get => CapturedAtUtc.ToString("O", CultureInfo.InvariantCulture);
        set => CapturedAtUtc = DateTimeOffset.Parse(
            value,
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal);
    }

    [DataMember(Name = "device_key", Order = 2)]
    public string DeviceKey { get; private set; } = "unknown";

    public IReadOnlyList<CapabilityEntry> Entries => entries;

    [DataMember(Name = "entries", Order = 3)]
    private CapabilityEntry[] EntriesWire
    {
        get => entries;
        set => entries = value ?? Array.Empty<CapabilityEntry>();
    }
}

public static class CapabilityWireCodec
{
    private static readonly DataContractJsonSerializer Serializer = new(typeof(CapabilityInventory));

    public static string Serialize(CapabilityInventory inventory)
    {
        if (inventory is null)
        {
            throw new ArgumentNullException(nameof(inventory));
        }

        using var stream = new MemoryStream();
        Serializer.WriteObject(stream, inventory);
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static CapabilityInventory Deserialize(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        return Serializer.ReadObject(stream) as CapabilityInventory
            ?? throw new InvalidDataException("Payload did not contain a capability inventory.");
    }
}
