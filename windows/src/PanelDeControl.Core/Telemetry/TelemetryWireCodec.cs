using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Telemetry;

public static class TelemetryWireCodec
{
    private static readonly DataContractJsonSerializer Serializer =
        new(typeof(HardwareSnapshot));

    public static string Serialize(HardwareSnapshot snapshot)
    {
        if (snapshot is null)
        {
            throw new ArgumentNullException(nameof(snapshot));
        }

        using var stream = new MemoryStream();
        Serializer.WriteObject(stream, snapshot.Normalize());
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    public static HardwareSnapshot Deserialize(string payload)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            throw new ArgumentException("Payload must not be empty.", nameof(payload));
        }

        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        var snapshot = Serializer.ReadObject(stream) as HardwareSnapshot;
        if (snapshot is null)
        {
            throw new InvalidDataException("Telemetry payload did not contain a snapshot.");
        }

        return snapshot.Normalize();
    }
}
