namespace PanelDeControl.Core.Telemetry;

public enum HardwareKind
{
    Unknown,
    Cpu,
    Gpu,
    Battery,
    Memory,
    Fan,
}

public enum SensorKind
{
    Unknown,
    Temperature,
    Load,
    Level,
    Power,
    Fan,
}

public sealed class SensorCandidate
{
    public SensorCandidate(
        string identifier,
        HardwareKind hardwareKind,
        SensorKind sensorKind,
        string name,
        double? value,
        string source)
    {
        Identifier = identifier;
        HardwareKind = hardwareKind;
        SensorKind = sensorKind;
        Name = name;
        Value = value;
        Source = source;
    }

    public string Identifier { get; }

    public HardwareKind HardwareKind { get; }

    public SensorKind SensorKind { get; }

    public string Name { get; }

    public double? Value { get; }

    public string Source { get; }
}
