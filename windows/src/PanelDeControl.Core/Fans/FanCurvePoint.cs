namespace PanelDeControl.Core.Fans;

public sealed class FanCurvePoint
{
    public FanCurvePoint(int temperature, int pwm)
    {
        Temperature = temperature;
        Pwm = pwm;
    }

    public int Temperature { get; }

    public int Pwm { get; }
}
