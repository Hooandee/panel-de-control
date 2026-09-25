using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Controls;
using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class CpuControllerTests
{
    [Fact]
    public void DisablingBoostIsAppliedOnlyWhenTheSchemeReadsBackDisabled()
    {
        var settings = new FakeSettings(boostMode: 2, maximum: 100);
        var response = new CpuController(settings).SetBoost(false);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.False(response.BoostEnabled);
        Assert.Equal(0u, settings.BoostMode);
    }

    [Fact]
    public void ReenablingBoostRestoresThePreviousMode()
    {
        var settings = new FakeSettings(boostMode: 4, maximum: 100);
        var controller = new CpuController(settings);

        controller.SetBoost(false);
        var response = controller.SetBoost(true);

        Assert.Equal(ControlStatus.Applied, response.Status);
        Assert.Equal(4u, settings.BoostMode);
    }

    [Fact]
    public void WriteThatDoesNotStickIsUnverifiable()
    {
        var settings = new FakeSettings(boostMode: 2, maximum: 100) { Sticks = false };
        var response = new CpuController(settings).SetMaximumState(60);

        Assert.Equal(ControlStatus.Unverifiable, response.Status);
        Assert.Equal(100, response.MaximumStatePercent);
        Assert.Equal("power_settings_mismatch", response.ErrorCode);
    }

    [Fact]
    public void DeniedWriteAsksForPermissionWithoutClaimingAState()
    {
        var settings = new FakeSettings(boostMode: 2, maximum: 100) { DenyWrites = true };
        var response = new CpuController(settings).SetMaximumState(60);

        Assert.Equal(ControlStatus.PermissionRequired, response.Status);
        Assert.Null(response.MaximumStatePercent);
    }

    [Fact]
    public void OutOfRangeStateNeverReachesTheScheme()
    {
        var settings = new FakeSettings(boostMode: 2, maximum: 100);
        var response = new CpuController(settings).SetMaximumState(0);

        Assert.Equal(ControlStatus.Rejected, response.Status);
        Assert.Equal(0, settings.Writes);
    }

    [Fact]
    public void ImplausibleSchemeValueIsNeverRoundedIntoAState()
    {
        var response = new CpuController(new FakeSettings(boostMode: 2, maximum: 0)).Get();

        Assert.Equal(ControlStatus.Unavailable, response.Status);
        Assert.Null(response.MaximumStatePercent);
    }

    [Fact]
    public async Task PipeServerReturnsTheActiveSchemeState()
    {
        var pipeName = $"pcpu-{Guid.NewGuid():N}";
        var server = new CpuControlPipeServer(
            pipeName,
            new CpuController(new FakeSettings(boostMode: 2, maximum: 90)),
            name => new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));

        var serverTask = server.RunOnceAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await client.ConnectAsync(timeout.Token);
        await using var writer = new StreamWriter(client, new UTF8Encoding(false), leaveOpen: true) { AutoFlush = true };
        using var reader = new StreamReader(client, leaveOpen: true);
        await writer.WriteLineAsync(CpuControlWireCodec.SerializeRequest(CpuControlRequest.Get()));
        var response = CpuControlWireCodec.DeserializeResponse((await reader.ReadLineAsync(timeout.Token))!);
        await serverTask;

        Assert.Equal(ControlStatus.Available, response.Status);
        Assert.True(response.BoostEnabled);
        Assert.Equal(90, response.MaximumStatePercent);
    }

    private sealed class FakeSettings : IProcessorPowerSettings
    {
        public FakeSettings(uint boostMode, uint maximum)
        {
            BoostMode = boostMode;
            Maximum = maximum;
        }

        public uint BoostMode { get; private set; }

        public uint Maximum { get; private set; }

        public bool Sticks { get; init; } = true;

        public bool DenyWrites { get; init; }

        public int Writes { get; private set; }

        public ProcessorPowerState? ReadActive(out bool accessDenied)
        {
            accessDenied = false;
            return new ProcessorPowerState(BoostMode, Maximum);
        }

        public PowerSettingsWrite Write(uint? boostMode, uint? maximumStatePercent)
        {
            Writes++;
            if (DenyWrites)
            {
                return PowerSettingsWrite.AccessDenied;
            }

            if (Sticks)
            {
                BoostMode = boostMode ?? BoostMode;
                Maximum = maximumStatePercent ?? Maximum;
            }

            return PowerSettingsWrite.Applied;
        }
    }
}
