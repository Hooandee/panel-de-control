using System.Runtime.InteropServices;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class CoreAudioVolumeControllerTests
{
    [Fact]
    public void DefaultProviderFailsClosedOutsideWindows()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var provider = new CoreAudioEndpointVolumeProvider();

        Assert.Throws<PlatformNotSupportedException>(
            provider.OpenDefaultRenderEndpoint);
    }

    [Fact]
    public void GetReturnsTheObservedDefaultEndpointLevelAndMuteState()
    {
        var provider = new FixedEndpointProvider(0.30, muted: true);
        var controller = new CoreAudioVolumeController(provider);

        var response = controller.Get();

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.Equal(0.30, response.ObservedLevel);
        Assert.True(response.ObservedMuted);
        Assert.Null(response.RequestedLevel);
        Assert.Null(response.RequestedMuted);
        Assert.Equal(1, provider.OpenCount);
    }

    [Fact]
    public void SetReportsAppliedOnlyAfterReadingTheRequestedLevelBack()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(0.30));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(0.55, response.RequestedLevel);
        Assert.Equal(0.55, response.ObservedLevel);
    }

    [Fact]
    public void SetReportsUnverifiableWhenTheEndpointReadbackDoesNotMatch()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(0.30, forcedReadback: 0.42));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(0.55, response.RequestedLevel);
        Assert.Equal(0.42, response.ObservedLevel);
        Assert.Equal("volume_readback_mismatch", response.ErrorCode);
    }

    [Fact]
    public void SetMuteReportsAppliedOnlyAfterReadingTheExactRequestedMuteStateBack()
    {
        var provider = new FixedEndpointProvider(0.30, muted: false);
        var controller = new CoreAudioVolumeController(provider);

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.True(response.RequestedMuted);
        Assert.True(response.ObservedMuted);
        Assert.Null(response.RequestedLevel);
        Assert.Null(response.ObservedLevel);
        Assert.Equal(1, provider.OpenCount);
    }

    [Fact]
    public void SetMuteReportsUnverifiableWhenTheEndpointReadbackDoesNotMatch()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                muted: false,
                forcedMuteReadback: false));

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.True(response.RequestedMuted);
        Assert.False(response.ObservedMuted);
        Assert.Equal("mute_readback_mismatch", response.ErrorCode);
    }

    [Fact]
    public void SetMuteReportsUnverifiableWhenReadbackFailsAfterTheWrite()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                readMuteExceptionAfterSet:
                    new InvalidOperationException("private endpoint identifier")));

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.True(response.RequestedMuted);
        Assert.Null(response.ObservedMuted);
        Assert.Equal("mute_readback_failed", response.ErrorCode);
    }

    [Fact]
    public void SetMuteMapsAccessDenialToPermissionRequired()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                setMuteException: new UnauthorizedAccessException("private account")));

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.PermissionRequired, response.Status);
        Assert.Equal("audio_permission_required", response.ErrorCode);
    }

    [Fact]
    public void SetMuteMapsAMissingDefaultEndpointToUnavailable()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new COMException(
                    "private endpoint identifier",
                    unchecked((int)0x80070490))));

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("audio_endpoint_unavailable", response.ErrorCode);
    }

    [Fact]
    public void SetMuteMapsUnexpectedProviderFailureWithoutLeakingItsMessage()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new InvalidOperationException("private endpoint identifier")));

        var response = controller.SetMute(true);

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("volume_provider_failed", response.ErrorCode);
        Assert.DoesNotContain(
            "private endpoint identifier",
            VolumeControlWireCodec.SerializeResponse(response));
    }

    [Fact]
    public void GetMapsAMissingDefaultEndpointToUnavailable()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new COMException(
                    "private endpoint identifier",
                    unchecked((int)0x80070490))));

        var response = controller.Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("audio_endpoint_unavailable", response.ErrorCode);
        Assert.DoesNotContain(
            "private endpoint identifier",
            VolumeControlWireCodec.SerializeResponse(response));
    }

    [Fact]
    public void GetMapsAccessDenialToPermissionRequired()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new UnauthorizedAccessException("private account")));

        var response = controller.Get();

        Assert.Equal(ControlStatus.PermissionRequired, response.Status);
        Assert.Equal("audio_permission_required", response.ErrorCode);
    }

    [Fact]
    public void GetMapsUnexpectedProviderFailureWithoutLeakingItsMessage()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new InvalidOperationException("private endpoint identifier")));

        var response = controller.Get();

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("volume_provider_failed", response.ErrorCode);
        Assert.DoesNotContain(
            "private endpoint identifier",
            VolumeControlWireCodec.SerializeResponse(response));
    }

    [Theory]
    [InlineData(-0.01)]
    [InlineData(1.01)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void SetRejectsLevelsOutsideTheCoreAudioScalarRange(double requestedLevel)
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(0.30));

        var response = controller.Set(requestedLevel);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("invalid_volume_level", response.ErrorCode);
    }

    [Fact]
    public void SetReportsUnverifiableWhenReadbackFailsAfterTheWrite()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                readExceptionAfterSet:
                    new InvalidOperationException("private endpoint identifier")));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(0.55, response.RequestedLevel);
        Assert.Null(response.ObservedLevel);
        Assert.Equal("volume_readback_failed", response.ErrorCode);
    }

    [Fact]
    public void SetMapsAccessDenialToPermissionRequired()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                setException: new UnauthorizedAccessException("private account")));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.PermissionRequired, response.Status);
        Assert.Equal("audio_permission_required", response.ErrorCode);
    }

    [Fact]
    public void SetMapsAMissingDefaultEndpointToUnavailable()
    {
        var controller = new CoreAudioVolumeController(
            new ThrowingEndpointProvider(
                new COMException(
                    "private endpoint identifier",
                    unchecked((int)0x80070490))));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("audio_endpoint_unavailable", response.ErrorCode);
    }

    [Fact]
    public void SetMapsUnexpectedWriteFailureToFault()
    {
        var controller = new CoreAudioVolumeController(
            new FixedEndpointProvider(
                0.30,
                setException:
                    new InvalidOperationException("private endpoint identifier")));

        var response = controller.Set(0.55);

        Assert.Equal(ControlStatus.Fault, response.Status);
        Assert.Equal("volume_provider_failed", response.ErrorCode);
    }

    private sealed class FixedEndpointProvider : IAudioEndpointVolumeProvider
    {
        private readonly double level;
        private readonly bool muted;
        private readonly double? forcedReadback;
        private readonly Exception? readExceptionAfterSet;
        private readonly Exception? setException;
        private readonly bool? forcedMuteReadback;
        private readonly Exception? readMuteExceptionAfterSet;
        private readonly Exception? setMuteException;

        public int OpenCount { get; private set; }

        public FixedEndpointProvider(
            double level,
            bool muted = false,
            double? forcedReadback = null,
            Exception? readExceptionAfterSet = null,
            Exception? setException = null,
            bool? forcedMuteReadback = null,
            Exception? readMuteExceptionAfterSet = null,
            Exception? setMuteException = null)
        {
            this.level = level;
            this.muted = muted;
            this.forcedReadback = forcedReadback;
            this.readExceptionAfterSet = readExceptionAfterSet;
            this.setException = setException;
            this.forcedMuteReadback = forcedMuteReadback;
            this.readMuteExceptionAfterSet = readMuteExceptionAfterSet;
            this.setMuteException = setMuteException;
        }

        public IAudioEndpointVolumeSession OpenDefaultRenderEndpoint()
        {
            OpenCount++;
            return new FixedEndpointSession(
                level,
                muted,
                forcedReadback,
                readExceptionAfterSet,
                setException,
                forcedMuteReadback,
                readMuteExceptionAfterSet,
                setMuteException);
        }
    }

    private sealed class FixedEndpointSession : IAudioEndpointVolumeSession
    {
        private double level;
        private bool muted;
        private readonly double? forcedReadback;
        private readonly Exception? readExceptionAfterSet;
        private readonly Exception? setException;
        private readonly bool? forcedMuteReadback;
        private readonly Exception? readMuteExceptionAfterSet;
        private readonly Exception? setMuteException;
        private bool setCalled;
        private bool setMuteCalled;

        public FixedEndpointSession(
            double level,
            bool muted,
            double? forcedReadback,
            Exception? readExceptionAfterSet,
            Exception? setException,
            bool? forcedMuteReadback,
            Exception? readMuteExceptionAfterSet,
            Exception? setMuteException)
        {
            this.level = level;
            this.muted = muted;
            this.forcedReadback = forcedReadback;
            this.readExceptionAfterSet = readExceptionAfterSet;
            this.setException = setException;
            this.forcedMuteReadback = forcedMuteReadback;
            this.readMuteExceptionAfterSet = readMuteExceptionAfterSet;
            this.setMuteException = setMuteException;
        }

        public double GetMasterVolumeLevel()
        {
            if (setCalled && readExceptionAfterSet is not null)
            {
                throw readExceptionAfterSet;
            }

            return level;
        }

        public void SetMasterVolumeLevel(double requestedLevel)
        {
            if (setException is not null)
            {
                throw setException;
            }

            setCalled = true;
            level = forcedReadback ?? requestedLevel;
        }

        public bool GetMute()
        {
            if (setMuteCalled && readMuteExceptionAfterSet is not null)
            {
                throw readMuteExceptionAfterSet;
            }

            return muted;
        }

        public void SetMute(bool requestedMuted)
        {
            if (setMuteException is not null)
            {
                throw setMuteException;
            }

            setMuteCalled = true;
            muted = forcedMuteReadback ?? requestedMuted;
        }

        public void Dispose()
        {
        }
    }

    private sealed class ThrowingEndpointProvider : IAudioEndpointVolumeProvider
    {
        private readonly Exception exception;

        public ThrowingEndpointProvider(Exception exception)
        {
            this.exception = exception;
        }

        public IAudioEndpointVolumeSession OpenDefaultRenderEndpoint()
        {
            throw exception;
        }
    }
}
