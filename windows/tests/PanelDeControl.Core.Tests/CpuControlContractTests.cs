using PanelDeControl.Core.Controls;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class CpuControlContractTests
{
    [Fact]
    public void AppliedResponseRoundTrips()
    {
        var wire = CpuControlWireCodec.SerializeResponse(CpuControlResponse.Applied(false, 80));
        var response = CpuControlWireCodec.DeserializeResponse(wire);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.False(response.BoostEnabled);
        Assert.Equal(80, response.MaximumStatePercent);
    }

    [Theory]
    [InlineData("{\"operation\":1}")]
    [InlineData("{\"operation\":2,\"maximum_state_percent\":0}")]
    [InlineData("{\"operation\":2,\"maximum_state_percent\":120}")]
    [InlineData("{\"operation\":0,\"boost_enabled\":true}")]
    [InlineData("{\"operation\":1,\"boost_enabled\":true,\"maximum_state_percent\":50}")]
    public void MalformedRequestsAreRejected(string payload)
    {
        Assert.Throws<InvalidDataException>(() => CpuControlWireCodec.DeserializeRequest(payload));
    }

    [Fact]
    public void FailuresNeverCarryAnObservedState()
    {
        var wire = CpuControlWireCodec.SerializeResponse(CpuControlResponse.PermissionRequired("power_settings_permission_required"));

        Assert.DoesNotContain("boost_enabled", wire);
        Assert.DoesNotContain("maximum_state_percent", wire);
    }

    [Fact]
    public void RequestsRoundTrip()
    {
        var boost = CpuControlWireCodec.DeserializeRequest(CpuControlWireCodec.SerializeRequest(CpuControlRequest.SetBoost(true)));
        var state = CpuControlWireCodec.DeserializeRequest(CpuControlWireCodec.SerializeRequest(CpuControlRequest.SetMaximumState(60)));

        Assert.True(boost.BoostEnabled);
        Assert.Equal(60, state.MaximumStatePercent);
    }
}
