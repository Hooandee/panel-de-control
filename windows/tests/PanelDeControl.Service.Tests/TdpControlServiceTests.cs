using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Devices;
using PanelDeControl.Hardware;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class TdpControlServiceTests
{
    private static readonly AsusTdpRegister[] ExpectedRegisters =
    {
        AsusTdpRegister.Pl1Spl,
        AsusTdpRegister.Sppt,
        AsusTdpRegister.Fppt,
    };

    [Fact]
    public void ExperimentalWritesAreDisabledByDefault()
    {
        var transport = new FakeTransport();
        var control = Create(transport: transport);

        var response = control.Set(25);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("experimental_tdp_disabled", response.ErrorCode);
        Assert.Empty(transport.Writes);
    }

    [Fact]
    public void BatterySetClampsEveryRegisterToTheCatalogCeiling()
    {
        var power = new FakePowerSource(AcPowerState.Battery);
        var transport = new FakeTransport();
        var control = Create(power: power, transport: transport);
        control.EnableExperimental();
        var readsBeforeSet = power.ReadCount;

        var response = control.Set(40);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(25, response.TargetWatts);
        Assert.Equal(25, response.AppliedWatts);
        Assert.Equal(readsBeforeSet + 1, power.ReadCount);
        Assert.Equal(
            ExpectedRegisters.Select(register => (register, 25)),
            transport.Writes);
    }

    [Fact]
    public void ChargerSetUsesTheFreshChargerCeiling()
    {
        var power = new FakePowerSource(AcPowerState.Battery);
        var transport = new FakeTransport();
        var control = Create(power: power, transport: transport);
        control.EnableExperimental();
        power.State = AcPowerState.External;

        var response = control.Set(40);

        Assert.Equal(35, response.TargetWatts);
        Assert.Equal(
            ExpectedRegisters.Select(register => (register, 35)),
            transport.Writes);
    }

    [Fact]
    public void ArmouryCrateBlocksBeforePowerOrFirmwareAccess()
    {
        var power = new FakePowerSource(AcPowerState.External);
        var transport = new FakeTransport();
        var rival = new FakeArmouryCrateGuard { Running = true };
        var control = Create(power: power, rival: rival, transport: transport);
        control.EnableExperimental();
        var readsBeforeSet = power.ReadCount;

        var response = control.Set(30);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("armoury_crate_running", response.ErrorCode);
        Assert.Equal(readsBeforeSet, power.ReadCount);
        Assert.Empty(transport.Writes);
    }

    [Fact]
    public void AvailableStateReportsArmouryCrateBeforeAWriteIsAttempted()
    {
        var transport = new FakeTransport();
        var rival = new FakeArmouryCrateGuard { Running = true };
        var control = Create(rival: rival, transport: transport);

        var response = control.Get();

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("armoury_crate_running", response.ErrorCode);
        Assert.Equal(7, response.MinimumWatts);
        Assert.Equal(25, response.MaximumWatts);
        Assert.Empty(transport.Writes);
        Assert.Empty(transport.Reads);
    }

    [Fact]
    public void FirmwareRejectionIsRejectedNotUnverifiable()
    {
        var transport = new FakeTransport
        {
            WriteResult = AsusTdpWriteResult.Rejected,
        };
        var control = Create(transport: transport);
        control.EnableExperimental();

        var response = control.Set(25);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal("firmware_rejected", response.ErrorCode);
        Assert.Null(response.AppliedWatts);
        Assert.Equal(3, transport.Writes.Count);
        Assert.Empty(transport.Reads);
    }

    [Fact]
    public void AcceptedWriteWithoutThreeMatchingDstsValuesIsUnverifiable()
    {
        var transport = new FakeTransport();
        transport.ReadValues[AsusTdpRegister.Fppt] = 24;
        var control = Create(transport: transport);
        control.EnableExperimental();

        var response = control.Set(25);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal("readback_mismatch", response.ErrorCode);
        Assert.Null(response.AppliedWatts);
        Assert.Equal(ExpectedRegisters, transport.Reads);
    }

    [Fact]
    public void AcceptedWriteWithoutReliableDstsIsUnverifiable()
    {
        var transport = new FakeTransport();
        transport.ReadResults[AsusTdpRegister.Sppt] =
            AsusTdpReadResult.Unavailable;
        var control = Create(transport: transport);
        control.EnableExperimental();

        var response = control.Set(25);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal("readback_unavailable", response.ErrorCode);
        Assert.Null(response.AppliedWatts);
    }

    [Fact]
    public void DisablingStopsWritesAndReturnsTheUnverifiedRecoveryAdvice()
    {
        var transport = new FakeTransport();
        var control = Create(transport: transport);
        control.EnableExperimental();

        var disabled = control.DisableExperimental();
        var response = control.Set(25);

        Assert.True(disabled.ManufacturerRecoveryUnverified);
        Assert.False(disabled.ExperimentalEnabled);
        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Empty(transport.Writes);
    }

    [Fact]
    public void UnknownPowerSourceNeverWrites()
    {
        var transport = new FakeTransport();
        var control = Create(
            power: new FakePowerSource(AcPowerState.Unknown),
            transport: transport);
        control.EnableExperimental();

        var response = control.Set(25);

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("power_source_unknown", response.ErrorCode);
        Assert.Empty(transport.Writes);
    }

    [Fact]
    public void OtherProfilesNeverReachTheTransport()
    {
        var transport = new FakeTransport();
        var control = Create(
            identity: new FixedIdentityReader(Identity("ROG Ally X")),
            transport: transport);

        var response = control.EnableExperimental();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Equal("tdp_profile_unsupported", response.ErrorCode);
        Assert.Empty(transport.Writes);
    }

    private static TdpControlService Create(
        IDeviceIdentityReader? identity = null,
        FakePowerSource? power = null,
        FakeArmouryCrateGuard? rival = null,
        FakeTransport? transport = null)
    {
        return new TdpControlService(
            identity ?? new FixedIdentityReader(Identity("ROG Xbox Ally X")),
            power ?? new FakePowerSource(AcPowerState.Battery),
            rival ?? new FakeArmouryCrateGuard(),
            transport ?? new FakeTransport());
    }

    private static DeviceIdentity Identity(string productName)
    {
        const string catalogJson = """
            {
              "schema_version": 1,
              "generic": {
                "key": "generic", "display_name": "Generic", "vendor": "amd",
                "chip": "Unknown", "experimental": false, "match_names": [],
                "dmi_matches": [],
                "limits": { "tdp_min": 4, "tdp_default": 10, "tdp_max": 30,
                  "tdp_max_charger": 30, "charger_only_extra": false,
                  "tdp_presets": [] }
              },
              "profiles": [
                {
                  "key": "rog_xbox_ally_x", "display_name": "ROG Xbox Ally X",
                  "vendor": "amd", "chip": "AMD", "experimental": false,
                  "match_names": ["ROG Xbox Ally X"], "dmi_matches": [],
                  "limits": { "tdp_min": 7, "tdp_default": 17, "tdp_max": 25,
                    "tdp_max_charger": 35, "charger_only_extra": false,
                    "tdp_presets": [13, 17, 25, 30] }
                },
                {
                  "key": "rog_ally_x", "display_name": "ROG Ally X",
                  "vendor": "amd", "chip": "AMD", "experimental": false,
                  "match_names": ["ROG Ally X"], "dmi_matches": [],
                  "limits": { "tdp_min": 7, "tdp_default": 17, "tdp_max": 25,
                    "tdp_max_charger": 30, "charger_only_extra": true,
                    "tdp_presets": [13, 17, 25, 30] }
                }
              ]
            }
            """;
        return DeviceIdentity.FromDmi(
            DeviceCatalog.Parse(catalogJson),
            "ASUSTeK COMPUTER INC.",
            productName,
            "RC73XA");
    }

    private sealed class FixedIdentityReader : IDeviceIdentityReader
    {
        private readonly DeviceIdentity identity;

        public FixedIdentityReader(DeviceIdentity identity)
        {
            this.identity = identity;
        }

        public DeviceIdentity Read() => identity;
    }

    private sealed class FakePowerSource : IAcPowerSource
    {
        public FakePowerSource(AcPowerState state)
        {
            State = state;
        }

        public AcPowerState State { get; set; }

        public int ReadCount { get; private set; }

        public AcPowerState Read()
        {
            ReadCount++;
            return State;
        }
    }

    private sealed class FakeArmouryCrateGuard : IArmouryCrateGuard
    {
        public bool Running { get; set; }

        public bool IsRunning() => Running;
    }

    private sealed class FakeTransport : IAsusTdpTransport
    {
        public AsusTdpWriteResult WriteResult { get; set; } =
            AsusTdpWriteResult.Accepted;

        public List<(AsusTdpRegister Register, int Watts)> Writes { get; } = new();

        public List<AsusTdpRegister> Reads { get; } = new();

        public Dictionary<AsusTdpRegister, int> ReadValues { get; } =
            ExpectedRegisters.ToDictionary(register => register, _ => 25);

        public Dictionary<AsusTdpRegister, AsusTdpReadResult> ReadResults { get; } =
            new();

        public AsusTdpWriteResult Write(AsusTdpRegister register, int watts)
        {
            Writes.Add((register, watts));
            return WriteResult;
        }

        public AsusTdpReadResult Read(AsusTdpRegister register)
        {
            Reads.Add(register);
            return ReadResults.TryGetValue(register, out var result)
                ? result
                : AsusTdpReadResult.Value(ReadValues[register]);
        }
    }
}
