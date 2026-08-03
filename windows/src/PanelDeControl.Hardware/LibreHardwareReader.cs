using LibreHardwareMonitor.Hardware;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Hardware;

public sealed class LibreHardwareReader : IHardwareReader, IDisposable
{
    private Computer? computer;

    public IReadOnlyList<SensorCandidate> Read()
    {
        if (!OperatingSystem.IsWindows())
        {
            return Array.Empty<SensorCandidate>();
        }

        computer ??= OpenComputer();
        var readings = new List<LibreSensorReading>();
        foreach (var hardware in computer.Hardware)
        {
            ReadHardware(hardware, readings);
        }

        return LibreHardwareCandidateMapper.Map(readings);
    }

    public void Dispose()
    {
        computer?.Close();
        computer = null;
    }

    private static Computer OpenComputer()
    {
        var opened = new Computer
        {
            IsCpuEnabled = true,
            IsGpuEnabled = true,
        };
        opened.Open();
        return opened;
    }

    private static void ReadHardware(
        IHardware hardware,
        ICollection<LibreSensorReading> readings)
    {
        hardware.Update();
        foreach (var sensor in hardware.Sensors)
        {
            readings.Add(new LibreSensorReading(
                sensor.Identifier.ToString(),
                hardware.HardwareType.ToString(),
                sensor.SensorType.ToString(),
                sensor.Name,
                sensor.Value));
        }

        foreach (var child in hardware.SubHardware)
        {
            ReadHardware(child, readings);
        }
    }
}
