using System.Globalization;
using System.Runtime.Serialization;

namespace PanelDeControl.Core.Telemetry;

[DataContract]
public sealed class HardwareSnapshot
{
    private TelemetryReading[] readings = Array.Empty<TelemetryReading>();

    private HardwareSnapshot()
    {
    }

    public HardwareSnapshot(
        DateTimeOffset capturedAtUtc,
        string deviceModel,
        IEnumerable<TelemetryReading> readings)
    {
        CapturedAtUtc = capturedAtUtc.ToUniversalTime();
        DeviceModel = string.IsNullOrWhiteSpace(deviceModel) ? "Unknown device" : deviceModel;
        this.readings = readings?.ToArray() ?? throw new ArgumentNullException(nameof(readings));
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

    [DataMember(Name = "device_model", Order = 2)]
    public string DeviceModel { get; private set; } = "Unknown device";

    public IReadOnlyList<TelemetryReading> Readings => readings;

    [DataMember(Name = "readings", Order = 3)]
    private TelemetryReading[] ReadingsWire
    {
        get => readings;
        set => readings = value ?? Array.Empty<TelemetryReading>();
    }

    internal HardwareSnapshot Normalize()
    {
        return new HardwareSnapshot(
            CapturedAtUtc,
            DeviceModel,
            Readings.Select(reading => reading.Normalize()));
    }
}
