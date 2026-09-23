using PanelDeControl.Core.Presentation;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class PresentationTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("not-a-colour")]
    public void UnknownAccentFallsBackToTheDefault(string? id)
    {
        Assert.Equal("blue", AccentPalette.Resolve(id).Id);
    }

    [Theory]
    [InlineData(7, 7, 35, 0)]
    [InlineData(35, 7, 35, 1)]
    [InlineData(21, 7, 35, 0.5)]
    [InlineData(50, 7, 35, 1)]
    [InlineData(1, 7, 35, 0)]
    [InlineData(10, 10, 10, 0)]
    public void FractionIsClampedToTheRange(double watts, double min, double max, double expected)
    {
        Assert.Equal(expected, PowerArc.Fraction(watts, min, max), 6);
    }

    [Theory]
    [InlineData(0, PowerZone.Save)]
    [InlineData(0.19, PowerZone.Save)]
    [InlineData(0.2, PowerZone.Eco)]
    [InlineData(0.5, PowerZone.Balanced)]
    [InlineData(0.7, PowerZone.Hot)]
    [InlineData(1, PowerZone.Turbo)]
    public void ZonesSplitTheArcInFiveEvenBands(double fraction, PowerZone expected)
    {
        Assert.Equal(expected, PowerArc.ZoneFor(fraction));
    }

    [Theory]
    [InlineData(0, 0xFF29E066u)]
    [InlineData(1, 0xFFE04129u)]
    public void ArcColorRunsFromGreenToRedLikeLinux(double fraction, uint expected)
    {
        Assert.Equal(expected, PowerArc.ColorFor(fraction));
    }

    [Fact]
    public void ArcStartsBottomLeftAndEndsBottomRight()
    {
        var start = PowerArc.PointAt(0, 100, 100, 80);
        var end = PowerArc.PointAt(1, 100, 100, 80);

        Assert.True(start.X < 100 && start.Y > 100);
        Assert.True(end.X > 100 && end.Y > 100);
        Assert.Equal(start.Y, end.Y, 6);
        Assert.False(PowerArc.IsLargeArc(0.5));
        Assert.True(PowerArc.IsLargeArc(0.9));
    }
}
