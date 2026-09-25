using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Presentation;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class TdpPresentationStateTests
{
    [Fact]
    public void AvailableDefaultIsOnlyASelectionAndNeverAConfirmedValue()
    {
        var state = new TdpPresentationState();

        state.Observe(TdpControlResponse.Available(false, 7, 35,
            new[] { 13, 17, 25, 30 }, true, defaultWatts: 17));

        Assert.Equal(17, state.SelectedWatts);
        Assert.Null(state.AppliedWatts);
    }

    [Fact]
    public void PendingSelectionAndFailedWritesPreserveOnlyTheLastConfirmedValue()
    {
        var state = new TdpPresentationState();
        state.Observe(TdpControlResponse.Applied(true, 25, 25, 25,
            7, 35, new[] { 13, 17, 25, 30 }, true));

        state.Select(30, 7, 35);

        Assert.Equal(30, state.SelectedWatts);
        Assert.Equal(25, state.AppliedWatts);
        state.Observe(TdpControlResponse.Unverifiable(true, 30, 30,
            7, 35, new[] { 13, 17, 25, 30 }, true, "firmware_partially_applied"));
        Assert.Equal(30, state.SelectedWatts);
        Assert.Equal(25, state.AppliedWatts);
        state.Observe(TdpControlResponse.Rejected(true, 31, 31,
            7, 35, new[] { 13, 17, 25, 30 }, true, "firmware_rejected"));
        Assert.Equal(31, state.SelectedWatts);
        Assert.Equal(25, state.AppliedWatts);
    }

    [Fact]
    public void AvailableRefreshClampsTheSelectionWithoutInventingAnAppliedValue()
    {
        var state = new TdpPresentationState();
        state.Observe(TdpControlResponse.Applied(true, 35, 35, 35,
            7, 35, new[] { 13, 17, 25, 30 }, true));

        state.Observe(TdpControlResponse.Available(true, 7, 25,
            new[] { 13, 17, 25 }, false));

        Assert.Equal(25, state.SelectedWatts);
        Assert.Equal(35, state.AppliedWatts);
    }

    [Fact]
    public void UnknownReadbackBeforeAnySuccessfulWriteHasNoAppliedValue()
    {
        var state = new TdpPresentationState();
        state.Select(25, 7, 35);

        state.Observe(TdpControlResponse.Indeterminate(true, 25,
            "tdp_response_unavailable", experimentalStateKnown: false));

        Assert.Equal(25, state.SelectedWatts);
        Assert.Null(state.AppliedWatts);
    }
}
