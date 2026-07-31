using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class IntegratedDisplayBrightnessControllerTests
{
    [Theory]
    [InlineData(6u)]
    [InlineData(11u)]
    [InlineData(13u)]
    [InlineData(0x80000000u)]
    public void GetSelectsOneActiveWritableIntegratedDisplay(
        uint videoOutputTechnology)
    {
        var provider = new FakeBrightnessProvider(
            Capability(
                "DISPLAY\\INTERNAL_0",
                videoOutputTechnology,
                currentBrightness: 42));
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Get();

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.Equal(42, response.ObservedPercentage);
        Assert.Equal(1, provider.DiscoverCount);
        Assert.Equal(0, provider.SetCount);
    }

    [Fact]
    public void GetDoesNotClaimSupportForAnExternalMonitor()
    {
        var controller = new IntegratedDisplayBrightnessController(
            new FakeBrightnessProvider(
                Capability("DISPLAY\\HDMI_0", 5, currentBrightness: 70)));

        var response = controller.Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("integrated_display_unavailable", response.ErrorCode);
        Assert.Null(response.ObservedPercentage);
    }

    [Fact]
    public void GetFailsClosedWhenMoreThanOneIntegratedDisplayMatches()
    {
        var controller = new IntegratedDisplayBrightnessController(
            new FakeBrightnessProvider(
                Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40),
                Capability("DISPLAY\\INTERNAL_1", 11, currentBrightness: 60)));

        var response = controller.Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("integrated_display_ambiguous", response.ErrorCode);
    }

    [Fact]
    public void GetRequiresAnActiveDisplayWithWriteAndReadbackLevels()
    {
        var controller = new IntegratedDisplayBrightnessController(
            new FakeBrightnessProvider(
                Capability(
                    "DISPLAY\\INACTIVE",
                    11,
                    currentBrightness: 50,
                    active: false),
                Capability(
                    "DISPLAY\\READ_ONLY",
                    11,
                    currentBrightness: 50,
                    canSet: false),
                Capability(
                    "DISPLAY\\NO_LEVELS",
                    11,
                    currentBrightness: 50,
                    levels: Array.Empty<int>())));

        var response = controller.Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("integrated_display_unavailable", response.ErrorCode);
    }

    [Fact]
    public void SetWritesOnceAtTheNearestSupportedLevelAndReadsTheSameDisplayBack()
    {
        var provider = new FakeBrightnessProvider(
            Capability(
                "DISPLAY\\INTERNAL_0",
                11,
                currentBrightness: 25,
                levels: new[] { 0, 25, 50, 75, 100 }));
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(53);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Equal(50, response.ObservedPercentage);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal("DISPLAY\\INTERNAL_0", provider.LastSetInstanceName);
        Assert.Equal(50, provider.LastSetPercentage);
        Assert.Equal(1u, provider.LastSetTimeoutSeconds);
        Assert.Equal("DISPLAY\\INTERNAL_0", provider.LastReadInstanceName);
    }

    [Fact]
    public void SetAcceptsReadbackWithinOnePercentagePoint()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            ForcedReadback = 51,
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Equal(51, response.ObservedPercentage);
    }

    [Fact]
    public void SetKeepsAMismatchedReadbackVisibleWithoutRetrying()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            ForcedReadback = 55,
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Equal(55, response.ObservedPercentage);
        Assert.Equal("brightness_readback_mismatch", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(1, provider.ReadCount);
    }

    [Fact]
    public void SetDoesNotRetryWhenTheWriteTimesOut()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            SetException = new TimeoutException("private WMI details"),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Null(response.ObservedPercentage);
        Assert.Equal("brightness_control_timeout", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(0, provider.ReadCount);
    }

    [Fact]
    public void SetDoesNotStartAWriteWhileAnIndeterminateWriteIsStillActive()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            SetException = new BrightnessWriteInProgressException(),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Equal("brightness_write_busy", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(0, provider.ReadCount);
    }

    [Fact]
    public void SetTreatsANonzeroWmiReturnCodeAsFailure()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            SetResult = 1,
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("brightness_set_failed", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(0, provider.ReadCount);
    }

    [Fact]
    public void SetDoesNotClaimSuccessWhenReadbackFails()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            ReadException = new InvalidOperationException("private WMI details"),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Null(response.ObservedPercentage);
        Assert.Equal("brightness_readback_failed", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(1, provider.ReadCount);
    }

    [Fact]
    public void SetReportsAConcurrentReadWithoutClaimingSuccess()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            ReadException = new BrightnessReadInProgressException(),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(50, response.RequestedPercentage);
        Assert.Null(response.ObservedPercentage);
        Assert.Equal("brightness_read_busy", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(1, provider.ReadCount);
    }

    [Fact]
    public void SetMapsAccessDenialWithoutRetrying()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40))
        {
            SetException = new UnauthorizedAccessException("private WMI details"),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(50);

        Assert.Equal(ControlStatus.PermissionRequired, response.Status);
        Assert.Equal("brightness_permission_required", response.ErrorCode);
        Assert.Equal(1, provider.SetCount);
        Assert.Equal(0, provider.ReadCount);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(101)]
    public void SetRejectsOutOfRangeValuesBeforeOpeningWmi(int percentage)
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 40));
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Set(percentage);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("invalid_brightness_percentage", response.ErrorCode);
        Assert.Equal(0, provider.DiscoverCount);
        Assert.Equal(0, provider.SetCount);
    }

    [Fact]
    public void AFailedReadDoesNotPoisonLaterDiscovery()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 42))
        {
            DiscoveryFailuresRemaining = 1,
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var failed = controller.Get();
        var recovered = controller.Get();

        Assert.Equal(ControlStatus.Fault, failed.Status);
        Assert.Equal("brightness_provider_failed", failed.ErrorCode);
        Assert.Equal(ControlStatus.Available, recovered.Status);
        Assert.Equal(42, recovered.ObservedPercentage);
        Assert.Equal(2, provider.DiscoverCount);
    }

    [Fact]
    public void ActiveDiscoveryIsReportedWithoutStartingAnotherRead()
    {
        var provider = new FakeBrightnessProvider(
            Capability("DISPLAY\\INTERNAL_0", 11, currentBrightness: 42))
        {
            DiscoveryException = new BrightnessReadInProgressException(),
        };
        var controller = new IntegratedDisplayBrightnessController(provider);

        var response = controller.Get();

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("brightness_read_busy", response.ErrorCode);
        Assert.Equal(1, provider.DiscoverCount);
    }

    private static DisplayBrightnessCapability Capability(
        string instanceName,
        uint videoOutputTechnology,
        int currentBrightness,
        bool active = true,
        bool canSet = true,
        IReadOnlyList<int>? levels = null)
    {
        return new DisplayBrightnessCapability(
            instanceName,
            active,
            videoOutputTechnology,
            currentBrightness,
            levels ?? Enumerable.Range(0, 101).ToArray(),
            canSet);
    }

    private sealed class FakeBrightnessProvider : IDisplayBrightnessProvider
    {
        private readonly IReadOnlyList<DisplayBrightnessCapability> capabilities;

        public FakeBrightnessProvider(params DisplayBrightnessCapability[] capabilities)
        {
            this.capabilities = capabilities;
        }

        public int DiscoverCount { get; private set; }

        public int SetCount { get; private set; }

        public int ReadCount { get; private set; }

        public int DiscoveryFailuresRemaining { get; set; }

        public Exception? DiscoveryException { get; set; }

        public Exception? SetException { get; set; }

        public Exception? ReadException { get; set; }

        public uint SetResult { get; set; }

        public int? ForcedReadback { get; set; }

        public string? LastSetInstanceName { get; private set; }

        public int? LastSetPercentage { get; private set; }

        public uint? LastSetTimeoutSeconds { get; private set; }

        public string? LastReadInstanceName { get; private set; }

        public IReadOnlyList<DisplayBrightnessCapability> Discover()
        {
            DiscoverCount++;
            if (DiscoveryException is not null)
            {
                throw DiscoveryException;
            }

            if (DiscoveryFailuresRemaining > 0)
            {
                DiscoveryFailuresRemaining--;
                throw new InvalidOperationException("private WMI details");
            }

            return capabilities;
        }

        public uint SetBrightness(
            string instanceName,
            int percentage,
            uint timeoutSeconds)
        {
            SetCount++;
            LastSetInstanceName = instanceName;
            LastSetPercentage = percentage;
            LastSetTimeoutSeconds = timeoutSeconds;
            if (SetException is not null)
            {
                throw SetException;
            }

            ForcedReadback ??= percentage;
            return SetResult;
        }

        public int ReadBrightness(string instanceName)
        {
            ReadCount++;
            LastReadInstanceName = instanceName;
            if (ReadException is not null)
            {
                throw ReadException;
            }

            return ForcedReadback ?? throw new InvalidOperationException();
        }
    }
}
