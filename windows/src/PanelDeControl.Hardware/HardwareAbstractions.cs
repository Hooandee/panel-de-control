using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public interface IDeviceIdentityReader
{
    DeviceIdentity Read();
}

public interface IHardwareReader
{
    IReadOnlyList<SensorCandidate> Read();
}

public interface IPowerStatusReader
{
    IReadOnlyList<TelemetryReading> Read();
}

public interface IHardwareSnapshotProvider
{
    HardwareSnapshot Capture();
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}
