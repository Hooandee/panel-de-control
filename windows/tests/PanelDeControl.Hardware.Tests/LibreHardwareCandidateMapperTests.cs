using PanelDeControl.Core.Telemetry;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class LibreHardwareCandidateMapperTests
{
    [Fact]
    public void MapsCpuAndAmdGpuSensorsToPortableKinds()
    {
        var readings = new[]
        {
            new LibreSensorReading("cpu/0/temp/0", "Cpu", "Temperature", "CPU Package", 72),
            new LibreSensorReading("gpu/0/load/0", "GpuAmd", "Load", "GPU Core", 0),
        };

        var candidates = LibreHardwareCandidateMapper.Map(readings);

        Assert.Collection(
            candidates,
            candidate =>
            {
                Assert.Equal(HardwareKind.Cpu, candidate.HardwareKind);
                Assert.Equal(SensorKind.Temperature, candidate.SensorKind);
                Assert.Equal(72, candidate.Value);
            },
            candidate =>
            {
                Assert.Equal(HardwareKind.Gpu, candidate.HardwareKind);
                Assert.Equal(SensorKind.Load, candidate.SensorKind);
                Assert.Equal(0, candidate.Value);
            });
    }

    [Fact]
    public void IgnoresWritableControlsAndUnknownHardware()
    {
        var readings = new[]
        {
            new LibreSensorReading("gpu/0/control/0", "GpuAmd", "Control", "GPU Fan", 50),
            new LibreSensorReading("board/0/temp/0", "Motherboard", "Temperature", "Board", 44),
        };

        var candidates = LibreHardwareCandidateMapper.Map(readings);

        Assert.Empty(candidates);
    }
}
