using PanelDeControl.Core.Controls;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class VolumeControlContractTests
{
    [Fact]
    public void GetRequestRoundTripsWithoutInventingARequestedLevel()
    {
        var request = VolumeControlRequest.Get();

        var payload = VolumeControlWireCodec.SerializeRequest(request);
        var roundTrip = VolumeControlWireCodec.DeserializeRequest(payload);

        Assert.Equal(VolumeControlOperation.Get, roundTrip.Operation);
        Assert.Null(roundTrip.RequestedLevel);
    }

    [Fact]
    public void SetRequestRoundTripsWithoutChangingTheRequestedLevel()
    {
        var request = VolumeControlRequest.Set(0.45);

        var payload = VolumeControlWireCodec.SerializeRequest(request);
        var roundTrip = VolumeControlWireCodec.DeserializeRequest(payload);

        Assert.Equal(VolumeControlOperation.Set, roundTrip.Operation);
        Assert.Equal(0.45, roundTrip.RequestedLevel);
    }

    [Fact]
    public void SetMuteRequestRoundTripsWithoutInventingALevel()
    {
        var request = VolumeControlRequest.SetMute(true);

        var payload = VolumeControlWireCodec.SerializeRequest(request);
        var roundTrip = VolumeControlWireCodec.DeserializeRequest(payload);

        Assert.Equal(VolumeControlOperation.SetMute, roundTrip.Operation);
        Assert.True(roundTrip.RequestedMuted);
        Assert.Null(roundTrip.RequestedLevel);
    }

    [Theory]
    [InlineData("{\"operation\":2}")]
    [InlineData("{\"operation\":2,\"requested_level\":0.5,\"requested_muted\":true}")]
    [InlineData("{\"operation\":1,\"requested_muted\":true,\"requested_level\":0.5}")]
    public void DeserializationRejectsMuteRequestsWithAnInvalidShape(string payload)
    {
        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeRequest(payload));
    }

    [Theory]
    [InlineData(-0.01)]
    [InlineData(1.01)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(double.NegativeInfinity)]
    public void SetRequestRejectsLevelsThatWindowsCannotApply(double requestedLevel)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => VolumeControlRequest.Set(requestedLevel));
    }

    [Fact]
    public void DeserializationRejectsAnOutOfRangeSetLevel()
    {
        const string payload = """
            {"operation":1,"requested_level":1.5}
            """;

        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void DeserializationRejectsAGetRequestThatContainsAWriteValue()
    {
        const string payload = """
            {"operation":0,"requested_level":0.5}
            """;

        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void DeserializationRejectsAnUnknownOperation()
    {
        const string payload = """
            {"operation":99}
            """;

        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void AppliedResponseRoundTripsRequestedAndObservedLevels()
    {
        var response = VolumeControlResponse.Applied(0.50, 0.498);

        var payload = VolumeControlWireCodec.SerializeResponse(response);
        var roundTrip = VolumeControlWireCodec.DeserializeResponse(payload);

        Assert.Equal(ControlStatus.Applied, roundTrip.Status);
        Assert.Equal(0.50, roundTrip.RequestedLevel);
        Assert.Equal(0.498, roundTrip.ObservedLevel);
        Assert.Null(roundTrip.ErrorCode);
    }

    [Fact]
    public void AvailableResponseRoundTripsBothEndpointObservations()
    {
        var response = VolumeControlResponse.Available(0.72, true);

        var roundTrip = RoundTrip(response);

        Assert.Equal(ControlStatus.Available, roundTrip.Status);
        Assert.Null(roundTrip.RequestedLevel);
        Assert.Equal(0.72, roundTrip.ObservedLevel);
        Assert.Null(roundTrip.RequestedMuted);
        Assert.True(roundTrip.ObservedMuted);
        Assert.Null(roundTrip.ErrorCode);
    }

    [Theory]
    [InlineData("{\"status\":0,\"observed_level\":0.72}")]
    [InlineData("{\"status\":0,\"observed_muted\":true}")]
    public void DeserializationRejectsAvailableResponsesMissingAnObservation(
        string payload)
    {
        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeResponse(payload));
    }

    [Theory]
    [InlineData(ControlStatus.Unavailable, "audio_endpoint_unavailable")]
    [InlineData(ControlStatus.PermissionRequired, "audio_permission_required")]
    [InlineData(ControlStatus.Rejected, "invalid_volume_request")]
    [InlineData(ControlStatus.Fault, "volume_provider_failed")]
    public void FailureResponseRoundTripsWithoutInventingALevel(
        ControlStatus status,
        string errorCode)
    {
        var response = status switch
        {
            ControlStatus.Unavailable => VolumeControlResponse.Unavailable(errorCode),
            ControlStatus.PermissionRequired =>
                VolumeControlResponse.PermissionRequired(errorCode),
            ControlStatus.Rejected => VolumeControlResponse.Rejected(errorCode),
            ControlStatus.Fault => VolumeControlResponse.Fault(errorCode),
            _ => throw new InvalidOperationException(),
        };

        var roundTrip = RoundTrip(response);

        Assert.Equal(status, roundTrip.Status);
        Assert.Null(roundTrip.RequestedLevel);
        Assert.Null(roundTrip.ObservedLevel);
        Assert.Equal(errorCode, roundTrip.ErrorCode);
    }

    [Fact]
    public void UnverifiableResponseKeepsObservedReadbackVisible()
    {
        var response = VolumeControlResponse.Unverifiable(
            0.50,
            0.42,
            "volume_readback_mismatch");

        var roundTrip = RoundTrip(response);

        Assert.Equal(ControlStatus.Unverifiable, roundTrip.Status);
        Assert.Equal(0.50, roundTrip.RequestedLevel);
        Assert.Equal(0.42, roundTrip.ObservedLevel);
        Assert.Equal("volume_readback_mismatch", roundTrip.ErrorCode);
    }

    [Fact]
    public void MuteAppliedResponseRoundTripsRequestedAndObservedMuteState()
    {
        var response = VolumeControlResponse.MuteApplied(true, true);

        var roundTrip = RoundTrip(response);

        Assert.Equal(ControlStatus.Applied, roundTrip.Status);
        Assert.True(roundTrip.RequestedMuted);
        Assert.True(roundTrip.ObservedMuted);
        Assert.Null(roundTrip.RequestedLevel);
        Assert.Null(roundTrip.ObservedLevel);
        Assert.Null(roundTrip.ErrorCode);
    }

    [Fact]
    public void MuteUnverifiableResponseKeepsTheAvailableReadbackVisible()
    {
        var response = VolumeControlResponse.MuteUnverifiable(
            false,
            true,
            "mute_readback_mismatch");

        var roundTrip = RoundTrip(response);

        Assert.Equal(ControlStatus.Unverifiable, roundTrip.Status);
        Assert.False(roundTrip.RequestedMuted);
        Assert.True(roundTrip.ObservedMuted);
        Assert.Null(roundTrip.RequestedLevel);
        Assert.Null(roundTrip.ObservedLevel);
        Assert.Equal("mute_readback_mismatch", roundTrip.ErrorCode);
    }

    [Theory]
    [InlineData("{\"status\":1,\"requested_level\":0.5,\"observed_level\":0.5,\"requested_muted\":true,\"observed_muted\":true}")]
    [InlineData("{\"status\":1,\"requested_muted\":true}")]
    [InlineData("{\"status\":5,\"requested_muted\":false,\"observed_level\":0.5,\"error_code\":\"mute_readback_mismatch\"}")]
    public void DeserializationRejectsResponsesThatMixOrOmitControlValues(string payload)
    {
        Assert.Throws<InvalidDataException>(
            () => VolumeControlWireCodec.DeserializeResponse(payload));
    }

    private static VolumeControlResponse RoundTrip(VolumeControlResponse response)
    {
        return VolumeControlWireCodec.DeserializeResponse(
            VolumeControlWireCodec.SerializeResponse(response));
    }
}
