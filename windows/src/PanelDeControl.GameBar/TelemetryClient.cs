using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Telemetry;
using Windows.ApplicationModel;

namespace PanelDeControl.GameBar;

public sealed class TelemetryClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Telemetry";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan SnapshotTimeout = TimeSpan.FromSeconds(15);

    public async Task<HardwareSnapshot> GetSnapshotAsync()
    {
        var snapshot = await TryReadAsync();
        if (snapshot is not null)
        {
            return snapshot;
        }

        try
        {
            await FullTrustProcessLauncher.LaunchFullTrustProcessForCurrentAppAsync(
                "HardwareBroker");
            await Task.Delay(250);
        }
        catch
        {
            return Fault("broker_launch_failed");
        }

        return await TryReadAsync() ?? Fault("broker_unreachable");
    }

    private static async Task<HardwareSnapshot?> TryReadAsync()
    {
        try
        {
            using var pipe = new NamedPipeClientStream(
                ".",
                PipeName,
                PipeDirection.InOut,
                PipeOptions.Asynchronous);
            await pipe.ConnectAsync((int)ConnectTimeout.TotalMilliseconds);
            using var reader = new StreamReader(
                pipe,
                new UTF8Encoding(false),
                false,
                256,
                leaveOpen: true);
            using var writer = new StreamWriter(
                pipe,
                new UTF8Encoding(false),
                256,
                leaveOpen: true)
            {
                AutoFlush = true,
            };
            await writer.WriteLineAsync("snapshot");
            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(SnapshotTimeout)) != readTask)
            {
                return null;
            }

            var payload = await readTask;
            return string.IsNullOrWhiteSpace(payload)
                ? null
                : TelemetryWireCodec.Deserialize(payload);
        }
        catch
        {
            return null;
        }
    }

    private static HardwareSnapshot Fault(string errorCode)
    {
        return new HardwareSnapshot(
            DateTimeOffset.UtcNow,
            "Unknown device",
            new[]
            {
                TelemetryReading.Unavailable(
                    "broker.connection",
                    "Conexión",
                    "-",
                    ReadingStatus.Fault,
                    errorCode),
            });
    }
}
