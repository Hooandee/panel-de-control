using PanelDeControl.Core.Controls;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class RefreshRateContractTests
{
    [Fact]
    public void AppliedResponseRoundTripsWithSortedSupportedRates()
    {
        var wire = RefreshRateWireCodec.SerializeResponse(RefreshRateResponse.Applied(120, 120, new[] { 120, 60, 120 }));
        var response = RefreshRateWireCodec.DeserializeResponse(wire);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(120, response.ObservedHertz);
        Assert.Equal(new[] { 60, 120 }, response.Supported);
    }

    [Fact]
    public void AppliedMustMatchWhatWasRead()
    {
        Assert.Throws<InvalidDataException>(() =>
            RefreshRateWireCodec.SerializeResponse(RefreshRateResponse.Applied(120, 60, new[] { 60, 120 })));
    }

    [Theory]
    [InlineData("{\"operation\":1}")]
    [InlineData("{\"operation\":1,\"requested_hz\":5}")]
    [InlineData("{\"operation\":0,\"requested_hz\":60}")]
    public void MalformedRequestsAreRejected(string payload)
    {
        Assert.Throws<InvalidDataException>(() => RefreshRateWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void SetRequestRoundTrips()
    {
        var request = RefreshRateWireCodec.DeserializeRequest(RefreshRateWireCodec.SerializeRequest(RefreshRateRequest.Set(90)));

        Assert.Equal(RefreshRateOperation.Set, request.Operation);
        Assert.Equal(90, request.RequestedHertz);
    }
}
