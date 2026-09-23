using System.Text.Json;
using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Devices;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class TdpControlContractTests
{
    public static IEnumerable<object[]> SharedWindowsTdpCases()
    {
        var path = Path.Combine(
            AppContext.BaseDirectory,
            "Fixtures",
            "windows_tdp.json");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        foreach (var testCase in document.RootElement
                     .GetProperty("cases")
                     .EnumerateArray())
        {
            var input = testCase.GetProperty("input");
            yield return new object[]
            {
                testCase.GetProperty("id").GetString()!,
                input.GetProperty("profile").GetString()!,
                input.GetProperty("requested_watts").GetInt32(),
                input.GetProperty("external_power").GetBoolean(),
                testCase.GetProperty("expected").GetProperty("target_watts").GetInt32(),
            };
        }
    }

    private static DeviceProfile AllyX()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Devices", "catalog.json");
        return DeviceCatalog.Parse(File.ReadAllText(path)).Profiles
            .Single(profile => profile.Key == TdpLimitPolicy.SupportedProfileKey);
    }

    [Theory]
    [InlineData(false, 40, 25)]
    [InlineData(false, 4, 7)]
    [InlineData(true, 40, 35)]
    [InlineData(true, 30, 30)]
    public void PolicyClampsToTheFreshPowerSourceLimits(
        bool externalPower,
        int requestedWatts,
        int expectedWatts)
    {
        var target = TdpLimitPolicy.CreateTarget(
            AllyX(),
            requestedWatts,
            externalPower);

        Assert.Equal(requestedWatts, target.RequestedWatts);
        Assert.Equal(expectedWatts, target.TargetWatts);
        Assert.Equal(7, target.MinimumWatts);
        Assert.Equal(externalPower ? 35 : 25, target.MaximumWatts);
    }

    [Fact]
    public void PolicyRejectsEveryProfileExceptTheXboxAllyX()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Devices", "catalog.json");
        var other = DeviceCatalog.Parse(File.ReadAllText(path)).Profiles
            .Single(profile => profile.Key == "rog_ally_x");

        Assert.Throws<NotSupportedException>(() =>
            TdpLimitPolicy.CreateTarget(other, 20, externalPower: true));
    }

    [Theory]
    [MemberData(nameof(SharedWindowsTdpCases))]
    public void SharedFixtureMatchesTheCorePolicy(
        string id,
        string profileKey,
        int requestedWatts,
        bool externalPower,
        int expectedTargetWatts)
    {
        Assert.False(string.IsNullOrWhiteSpace(id));
        Assert.Equal(TdpLimitPolicy.SupportedProfileKey, profileKey);

        var target = TdpLimitPolicy.CreateTarget(
            AllyX(),
            requestedWatts,
            externalPower);

        Assert.Equal(expectedTargetWatts, target.TargetWatts);
    }

    [Fact]
    public void SetRequestRequiresAnIntegerAndOtherVerbsForbidIt()
    {
        var set = TdpControlRequest.Set(25);

        Assert.Equal(TdpControlOperation.Set, set.Operation);
        Assert.Equal(25, set.RequestedWatts);
        Assert.Throws<InvalidDataException>(() =>
            TdpControlWireCodec.DeserializeRequest(
                "{\"operation\":3,\"requested_watts\":25.5}"));
        Assert.Throws<InvalidDataException>(() =>
            TdpControlWireCodec.DeserializeRequest(
                "{\"operation\":0,\"requested_watts\":25}"));
    }

    [Fact]
    public void AppliedRequiresTheConfirmedTarget()
    {
        var response = TdpControlResponse.Applied(
            experimentalEnabled: true,
            requestedWatts: 40,
            targetWatts: 35,
            appliedWatts: 35,
            minimumWatts: 7,
            maximumWatts: 35,
            presetWatts: new[] { 13, 17, 25, 30 },
            externalPower: true);

        var roundTrip = TdpControlWireCodec.DeserializeResponse(
            TdpControlWireCodec.SerializeResponse(response));

        Assert.Equal(ControlStatus.Applied, roundTrip.Status);
        Assert.Equal(40, roundTrip.RequestedWatts);
        Assert.Equal(35, roundTrip.TargetWatts);
        Assert.Equal(35, roundTrip.AppliedWatts);
        Assert.True(roundTrip.ReadbackCandidateUnvalidated);
        Assert.Throws<ArgumentException>(() => TdpControlResponse.Applied(
            true,
            35,
            35,
            34,
            7,
            35,
            Array.Empty<int>(),
            true));
    }

    [Fact]
    public void AvailableStateCarriesTheCatalogDefaultForTheWidget()
    {
        var response = TdpControlResponse.Available(
            experimentalEnabled: false,
            minimumWatts: 7,
            maximumWatts: 25,
            presetWatts: new[] { 13, 17, 25 },
            externalPower: false,
            defaultWatts: 17);

        var roundTrip = TdpControlWireCodec.DeserializeResponse(
            TdpControlWireCodec.SerializeResponse(response));

        Assert.Equal(17, roundTrip.DefaultWatts);
    }

    [Fact]
    public void RejectedAndUnverifiableNeverCarryAppliedWatts()
    {
        var rejected = TdpControlResponse.Rejected(
            true,
            30,
            25,
            7,
            25,
            new[] { 13, 17, 25 },
            false,
            "firmware_rejected");
        var unverifiable = TdpControlResponse.Unverifiable(
            true,
            30,
            25,
            7,
            25,
            new[] { 13, 17, 25 },
            false,
            "readback_unavailable");

        Assert.Equal(ControlStatus.Rejected, rejected.Status);
        Assert.Null(rejected.AppliedWatts);
        Assert.Equal(ControlStatus.Unverifiable, unverifiable.Status);
        Assert.Null(unverifiable.AppliedWatts);
    }

    [Fact]
    public void TransportFailureDoesNotInventTheExperimentalState()
    {
        var response = TdpControlResponse.Fault(
            experimentalEnabled: false,
            "service_unavailable",
            experimentalStateKnown: false);

        var roundTrip = TdpControlWireCodec.DeserializeResponse(
            TdpControlWireCodec.SerializeResponse(response));

        Assert.False(roundTrip.ExperimentalStateKnown);
    }
}
