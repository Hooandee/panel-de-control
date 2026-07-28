namespace PanelDeControl.Core.Telemetry;

public sealed class TelemetrySample
{
    public int Pl1 { get; set; }

    public double? Watts { get; set; }

    public double? GpuBusy { get; set; }

    public double? Boost { get; set; }

    public double? CpuTemperature { get; set; }

    public double? GpuTemperature { get; set; }

    public double? FanRpm { get; set; }
}
