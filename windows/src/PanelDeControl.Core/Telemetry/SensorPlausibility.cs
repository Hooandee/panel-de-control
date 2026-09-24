namespace PanelDeControl.Core.Telemetry;

public static class SensorPlausibility
{
    public const double MaxTemperatureCelsius = 125;

    public static bool IsPlausible(SensorKind kind, double? value)
    {
        if (value is not double reading || double.IsNaN(reading) || double.IsInfinity(reading))
        {
            return false;
        }

        return kind switch
        {
            // Missing ring0 access yields zeroed registers, so an exact 0 °C is not a reading.
            SensorKind.Temperature => reading > 0 && reading <= MaxTemperatureCelsius,
            SensorKind.Load or SensorKind.Level => reading >= 0 && reading <= 100,
            SensorKind.Fan => reading >= 0 && reading <= 10_000,
            SensorKind.Power => reading >= -1_000 && reading <= 1_000,
            _ => false,
        };
    }
}
