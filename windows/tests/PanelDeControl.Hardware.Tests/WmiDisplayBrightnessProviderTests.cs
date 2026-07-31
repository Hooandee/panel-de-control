using System.Management;
using System.Runtime.Versioning;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class WmiDisplayBrightnessProviderTests
{
    [Fact]
    public void MapperRequiresMatchingActiveConnectionReadingAndMethodInstances()
    {
        var capabilities = WmiDisplayBrightnessCapabilityMapper.Map(
            new[]
            {
                new WmiMonitorConnection(
                    "DISPLAY\\INTERNAL_0",
                    Active: true,
                    VideoOutputTechnology: 11),
                new WmiMonitorConnection(
                    "DISPLAY\\EXTERNAL_0",
                    Active: true,
                    VideoOutputTechnology: 5),
            },
            new[]
            {
                new WmiMonitorBrightnessReading(
                    "display\\internal_0",
                    Active: true,
                    CurrentBrightness: 50,
                    Levels: new[] { 0, 25, 50, 75, 100 }),
                new WmiMonitorBrightnessReading(
                    "DISPLAY\\EXTERNAL_0",
                    Active: false,
                    CurrentBrightness: 70,
                    Levels: new[] { 0, 50, 100 }),
            },
            new[]
            {
                new WmiMonitorBrightnessMethod(
                    "DISPLAY\\INTERNAL_0",
                    Active: true),
            });

        var capability = Assert.Single(capabilities);
        Assert.Equal("DISPLAY\\INTERNAL_0", capability.InstanceName);
        Assert.True(capability.Active);
        Assert.Equal(11u, capability.VideoOutputTechnology);
        Assert.Equal(50, capability.CurrentBrightness);
        Assert.Equal(new[] { 0, 25, 50, 75, 100 }, capability.Levels);
        Assert.True(capability.CanSet);
    }

    [Fact]
    public void MapperKeepsReadOnlyCapabilityVisibleForHonestSelection()
    {
        var capabilities = WmiDisplayBrightnessCapabilityMapper.Map(
            new[]
            {
                new WmiMonitorConnection("DISPLAY\\INTERNAL_0", true, 11),
            },
            new[]
            {
                new WmiMonitorBrightnessReading(
                    "DISPLAY\\INTERNAL_0",
                    true,
                    50,
                    new[] { 0, 50, 100 }),
            },
            Array.Empty<WmiMonitorBrightnessMethod>());

        var capability = Assert.Single(capabilities);
        Assert.False(capability.CanSet);
    }

    [Fact]
    public void MapperDoesNotJoinDifferentMonitorInstances()
    {
        var capabilities = WmiDisplayBrightnessCapabilityMapper.Map(
            new[]
            {
                new WmiMonitorConnection("DISPLAY\\INTERNAL_0", true, 11),
            },
            new[]
            {
                new WmiMonitorBrightnessReading(
                    "DISPLAY\\INTERNAL_1",
                    true,
                    50,
                    new[] { 0, 50, 100 }),
            },
            new[]
            {
                new WmiMonitorBrightnessMethod(
                    "DISPLAY\\INTERNAL_0",
                    true),
            });

        Assert.Empty(capabilities);
    }

    [Fact]
    public void DefaultProviderFailsClosedOutsideWindows()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var provider = new WmiDisplayBrightnessProvider();

        Assert.Throws<PlatformNotSupportedException>(provider.Discover);
        Assert.Throws<PlatformNotSupportedException>(
            () => provider.SetBrightness("DISPLAY\\INTERNAL_0", 50, 1));
        Assert.Throws<PlatformNotSupportedException>(
            () => provider.ReadBrightness("DISPLAY\\INTERNAL_0"));
    }

    [Fact]
    public void NativeWmiFailuresMapToHonestControlStates()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        AssertMapping(
            ManagementStatus.AccessDenied,
            typeof(UnauthorizedAccessException));
        AssertMapping(
            ManagementStatus.Timedout,
            typeof(TimeoutException));
    }

    [SupportedOSPlatform("windows")]
    private static void AssertMapping(
        ManagementStatus status,
        Type expectedType)
    {
        var source = new ManagementException("private WMI details");

        var mapped = WmiManagementExceptionMapper.Translate(status, source);

        Assert.IsType(expectedType, mapped);
        Assert.Same(source, mapped.InnerException);
    }
}
