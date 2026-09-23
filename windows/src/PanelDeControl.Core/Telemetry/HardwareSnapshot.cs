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
        IEnumerable<TelemetryReading> readings,
        int? deviceMaxWatts = null)
    {
        CapturedAtUtc = capturedAtUtc.ToUniversalTime();
        DeviceModel = string.IsNullOrWhiteSpace(deviceModel) ? "Unknown device" : deviceModel;
        this.readings = readings?.ToArray() ?? throw new ArgumentNullException(nameof(readings));
        DeviceMaxWatts = deviceMaxWatts is > 0 ? deviceMaxWatts : null;
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

    [DataMember(Name = "device_max_watts", Order = 4, EmitDefaultValue = false)]
    public int? DeviceMaxWatts { get; private set; }

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
            Readings.Select(reading => reading.Normalize()),
            DeviceMaxWatts);
    }
}
