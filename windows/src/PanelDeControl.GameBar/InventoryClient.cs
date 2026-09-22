using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Capabilities;

namespace PanelDeControl.GameBar;

public sealed class InventoryClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Telemetry";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan InventoryTimeout = TimeSpan.FromSeconds(15);

    public async Task<CapabilityInventory?> GetInventoryAsync()
    {
        var inventory = await TryReadAsync();
        if (inventory is not null)
        {
            return inventory;
        }

        try
        {
            await HardwareBrokerLauncher.EnsureStartedAsync();
        }
        catch
        {
            return null;
        }

        return await TryReadAsync();
    }

    private static async Task<CapabilityInventory?> TryReadAsync()
    {
        try
        {
            using var pipe = new NamedPipeClientStream(
                ".",
                PipeName,
                PipeDirection.InOut,
                PipeOptions.Asynchronous);
            await pipe.ConnectAsync((int)ConnectTimeout.TotalMilliseconds);
            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 256, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 256, leaveOpen: true)
            {
                AutoFlush = true,
            };
            await writer.WriteLineAsync("inventory");
            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(InventoryTimeout)) != readTask)
            {
                return null;
            }

            var payload = await readTask;
            return string.IsNullOrWhiteSpace(payload)
                ? null
                : CapabilityWireCodec.Deserialize(payload);
        }
        catch
        {
            return null;
        }
    }
}
