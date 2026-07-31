using PanelDeControl.Core.Controls;
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

public interface IAudioEndpointVolumeProvider
{
    IAudioEndpointVolumeSession OpenDefaultRenderEndpoint();
}

public interface IAudioEndpointVolumeSession : IDisposable
{
    double GetMasterVolumeLevel();

    void SetMasterVolumeLevel(double requestedLevel);

    bool GetMute();

    void SetMute(bool requestedMuted);
}

public interface ISystemVolumeController
{
    VolumeControlResponse Get();

    VolumeControlResponse Set(double requestedLevel);

    VolumeControlResponse SetMute(bool requestedMuted);
}

public sealed record DisplayBrightnessCapability(
    string InstanceName,
    bool Active,
    uint VideoOutputTechnology,
    int CurrentBrightness,
    IReadOnlyList<int> Levels,
    bool CanSet);

public interface IDisplayBrightnessProvider
{
    IReadOnlyList<DisplayBrightnessCapability> Discover();

    uint SetBrightness(
        string instanceName,
        int percentage,
        uint timeoutSeconds);

    int ReadBrightness(string instanceName);
}

public interface IDisplayBrightnessController
{
    BrightnessControlResponse Get();

    BrightnessControlResponse Set(int requestedPercentage);
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}
