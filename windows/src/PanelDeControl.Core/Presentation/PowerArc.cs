namespace PanelDeControl.Core.Presentation;

public enum PowerZone
{
    Save,
    Eco,
    Balanced,
    Hot,
    Turbo,
}

public readonly struct ArcPoint
{
    public ArcPoint(double x, double y)
    {
        X = x;
        Y = y;
    }

    public double X { get; }

    public double Y { get; }
}

public static class PowerArc
{
    public const double StartDegrees = 135;
    public const double SweepDegrees = 270;

    private static readonly PowerZone[] Zones =
    {
        PowerZone.Save,
        PowerZone.Eco,
        PowerZone.Balanced,
        PowerZone.Hot,
        PowerZone.Turbo,
    };

    public static double Fraction(double watts, double minimum, double maximum)
    {
        var span = maximum - minimum;
        if (span <= 0 || double.IsNaN(watts))
        {
            return 0;
        }

        return Clamp((watts - minimum) / span);
    }

    public static PowerZone ZoneFor(double fraction)
    {
        var index = (int)Math.Floor(Clamp(fraction) * Zones.Length);
        return Zones[Math.Min(Zones.Length - 1, index)];
    }

    public static uint ColorFor(double fraction)
    {
        var hue = Math.Round(140 - (Clamp(fraction) * 132));
        return FromHsl(hue, 0.75, 0.52);
    }

    public static ArcPoint PointAt(double fraction, double centerX, double centerY, double radius)
    {
        var radians = (StartDegrees + (Clamp(fraction) * SweepDegrees)) * Math.PI / 180;
        return new ArcPoint(centerX + (radius * Math.Cos(radians)), centerY + (radius * Math.Sin(radians)));
    }

    public static bool IsLargeArc(double fraction)
    {
        return Clamp(fraction) * SweepDegrees > 180;
    }

    private static double Clamp(double value)
    {
        return double.IsNaN(value) ? 0 : Math.Min(Math.Max(value, 0), 1);
    }

    private static uint FromHsl(double hue, double saturation, double lightness)
    {
        var chroma = (1 - Math.Abs((2 * lightness) - 1)) * saturation;
        var segment = hue / 60;
        var secondary = chroma * (1 - Math.Abs((segment % 2) - 1));
        var (red, green, blue) = segment switch
        {
            < 1 => (chroma, secondary, 0d),
            < 2 => (secondary, chroma, 0d),
            < 3 => (0d, chroma, secondary),
            < 4 => (0d, secondary, chroma),
            < 5 => (secondary, 0d, chroma),
            _ => (chroma, 0d, secondary),
        };
        var offset = lightness - (chroma / 2);
        return 0xFF000000u |
            ((uint)Math.Round((red + offset) * 255) << 16) |
            ((uint)Math.Round((green + offset) * 255) << 8) |
            (uint)Math.Round((blue + offset) * 255);
    }
}
