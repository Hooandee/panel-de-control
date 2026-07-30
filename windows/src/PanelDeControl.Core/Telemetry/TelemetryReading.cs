using System.Runtime.Serialization;

namespace PanelDeControl.Core.Telemetry;

[DataContract]
public sealed class TelemetryReading
{
    private TelemetryReading()
    {
    }

    private TelemetryReading(
        string id,
        string label,
        ReadingStatus status,
        string unit,
        double? value,
        string? source,
        string? errorCode)
    {
        Id = RequireText(id, nameof(id));
        Label = RequireText(label, nameof(label));
        Status = status;
        Unit = RequireText(unit, nameof(unit));
        Value = value;
        Source = source;
        ErrorCode = errorCode;
    }

    [DataMember(Name = "id", Order = 1)]
    public string Id { get; private set; } = string.Empty;

    [DataMember(Name = "label", Order = 2)]
    public string Label { get; private set; } = string.Empty;

    [DataMember(Name = "status", Order = 3)]
    public ReadingStatus Status { get; private set; }

    [DataMember(Name = "unit", Order = 4)]
    public string Unit { get; private set; } = string.Empty;

    [DataMember(Name = "value", Order = 5, EmitDefaultValue = false)]
    public double? Value { get; private set; }

    [DataMember(Name = "source", Order = 6, EmitDefaultValue = false)]
    public string? Source { get; private set; }

    [DataMember(Name = "error_code", Order = 7, EmitDefaultValue = false)]
    public string? ErrorCode { get; private set; }

    public static TelemetryReading Available(
        string id,
        string label,
        double value,
        string unit,
        string source)
    {
        if (double.IsNaN(value) || double.IsInfinity(value))
        {
            throw new ArgumentOutOfRangeException(nameof(value));
        }

        return new TelemetryReading(
            id,
            label,
            ReadingStatus.Available,
            unit,
            value,
            RequireText(source, nameof(source)),
            null);
    }

    public static TelemetryReading Unavailable(
        string id,
        string label,
        string unit,
        ReadingStatus status,
        string errorCode)
    {
        if (status == ReadingStatus.Available || !Enum.IsDefined(typeof(ReadingStatus), status))
        {
            throw new ArgumentOutOfRangeException(nameof(status));
        }

        return new TelemetryReading(
            id,
            label,
            status,
            unit,
            null,
            null,
            RequireText(errorCode, nameof(errorCode)));
    }

    internal TelemetryReading Normalize()
    {
        if (!Enum.IsDefined(typeof(ReadingStatus), Status))
        {
            return Fault("invalid_reading_status");
        }

        if (Status == ReadingStatus.Available &&
            (!Value.HasValue || double.IsNaN(Value.Value) || double.IsInfinity(Value.Value)))
        {
            return Fault("invalid_reading_value");
        }

        if (Status != ReadingStatus.Available && Value.HasValue)
        {
            return Fault("value_present_for_unavailable_reading");
        }

        return this;
    }

    private TelemetryReading Fault(string errorCode)
    {
        return Unavailable(
            SafeText(Id, "unknown"),
            SafeText(Label, "Sensor"),
            SafeText(Unit, "-"),
            ReadingStatus.Fault,
            errorCode);
    }

    private static string RequireText(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Value must not be empty.", parameterName);
        }

        return value;
    }

    private static string SafeText(string? value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value!;
    }
}
