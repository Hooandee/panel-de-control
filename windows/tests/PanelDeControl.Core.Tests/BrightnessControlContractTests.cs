using PanelDeControl.Core.Controls;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class BrightnessControlContractTests
{
    [Fact]
    public void GetRequestRoundTripsWithoutInventingARequestedPercentage()
    {
        var roundTrip = RoundTrip(BrightnessControlRequest.Get());

        Assert.Equal(BrightnessControlOperation.Get, roundTrip.Operation);
        Assert.Null(roundTrip.RequestedPercentage);
    }

    [Fact]
    public void SetRequestRoundTripsTheRequestedPercentage()
    {
        var roundTrip = RoundTrip(BrightnessControlRequest.Set(45));

        Assert.Equal(BrightnessControlOperation.Set, roundTrip.Operation);
        Assert.Equal(45, roundTrip.RequestedPercentage);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(101)]
    public void SetRequestRejectsPercentagesOutsideTheWindowsRange(
        int requestedPercentage)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => BrightnessControlRequest.Set(requestedPercentage));
    }

    [Theory]
    [InlineData("{\"operation\":0,\"requested_percentage\":45}")]
    [InlineData("{\"operation\":1}")]
    [InlineData("{\"operation\":1,\"requested_percentage\":101}")]
    [InlineData("{\"operation\":99}")]
    public void DeserializationRejectsInvalidRequestShapes(string payload)
    {
        Assert.Throws<InvalidDataException>(
            () => BrightnessControlWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void AvailableResponseRoundTripsOnlyTheObservedPercentage()
    {
        var roundTrip = RoundTrip(BrightnessControlResponse.Available(62));

        Assert.Equal(ControlStatus.Available, roundTrip.Status);
        Assert.Null(roundTrip.RequestedPercentage);
        Assert.Equal(62, roundTrip.ObservedPercentage);
        Assert.Null(roundTrip.ErrorCode);
    }

    [Fact]
    public void AppliedResponseRoundTripsRequestedAndObservedPercentages()
    {
        var roundTrip = RoundTrip(BrightnessControlResponse.Applied(60, 61));

        Assert.Equal(ControlStatus.Applied, roundTrip.Status);
        Assert.Equal(60, roundTrip.RequestedPercentage);
        Assert.Equal(61, roundTrip.ObservedPercentage);
        Assert.Null(roundTrip.ErrorCode);
    }

    [Theory]
    [InlineData(ControlStatus.Unavailable, "integrated_display_unavailable")]
    [InlineData(ControlStatus.PermissionRequired, "brightness_permission_required")]
    [InlineData(ControlStatus.Rejected, "invalid_brightness_percentage")]
    [InlineData(ControlStatus.Fault, "brightness_provider_failed")]
    public void FailureResponseRoundTripsWithoutInventingAValue(
        ControlStatus status,
        string errorCode)
    {
        var response = status switch
        {
            ControlStatus.Unavailable => BrightnessControlResponse.Unavailable(errorCode),
            ControlStatus.PermissionRequired =>
                BrightnessControlResponse.PermissionRequired(errorCode),
            ControlStatus.Rejected => BrightnessControlResponse.Rejected(errorCode),
            ControlStatus.Fault => BrightnessControlResponse.Fault(errorCode),
            _ => throw new InvalidOperationException(),
        };

        var roundTrip = RoundTrip(response);

        Assert.Equal(status, roundTrip.Status);
        Assert.Null(roundTrip.RequestedPercentage);
        Assert.Null(roundTrip.ObservedPercentage);
        Assert.Equal(errorCode, roundTrip.ErrorCode);
    }

    [Fact]
    public void UnverifiableResponseKeepsTheObservedReadbackVisible()
    {
        var roundTrip = RoundTrip(
            BrightnessControlResponse.Unverifiable(
                60,
                50,
                "brightness_readback_mismatch"));

        Assert.Equal(ControlStatus.Unverifiable, roundTrip.Status);
        Assert.Equal(60, roundTrip.RequestedPercentage);
        Assert.Equal(50, roundTrip.ObservedPercentage);
        Assert.Equal("brightness_readback_mismatch", roundTrip.ErrorCode);
    }

    [Theory]
    [InlineData("{\"status\":0}")]
    [InlineData("{\"status\":1,\"observed_percentage\":50}")]
    [InlineData("{\"status\":2,\"observed_percentage\":50,\"error_code\":\"no_display\"}")]
    [InlineData("{\"status\":5,\"error_code\":\"readback_failed\"}")]
    public void DeserializationRejectsInvalidResponseShapes(string payload)
    {
        Assert.Throws<InvalidDataException>(
            () => BrightnessControlWireCodec.DeserializeResponse(payload));
    }

    private static BrightnessControlRequest RoundTrip(
        BrightnessControlRequest request)
    {
        return BrightnessControlWireCodec.DeserializeRequest(
            BrightnessControlWireCodec.SerializeRequest(request));
    }

    private static BrightnessControlResponse RoundTrip(
        BrightnessControlResponse response)
    {
        return BrightnessControlWireCodec.DeserializeResponse(
            BrightnessControlWireCodec.SerializeResponse(response));
    }
}
