using System.Diagnostics;
using System.Text;

namespace PanelDeControl.Hardware.NativeKeyboard;

public sealed class NativeKeyboardHost : INativeKeyboardHost
{
    private readonly string executable = Path.Combine(AppContext.BaseDirectory, "NativeKeyboard", "PanelDeControl.KeyboardHost.exe");
    public bool Available => File.Exists(executable) && File.Exists(Path.Combine(Path.GetDirectoryName(executable)!, "PanelDeControl.KeyboardTap.dll"));

    public async Task<string> DiscoverAsync(CancellationToken token)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo(executable, "discover")
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = Path.GetDirectoryName(executable)!,
            },
        };
        if (!process.Start()) throw new IOException("Runtime did not start.");
        try
        {
            var stdout = ReadBoundedAsync(process.StandardOutput, token);
            var stderr = ReadBoundedAsync(process.StandardError, token);
            await Task.WhenAll(stdout, stderr, process.WaitForExitAsync(token)).ConfigureAwait(false);
            if (process.ExitCode != 0) throw new IOException("Runtime exited unsuccessfully.");
            return await stdout.ConfigureAwait(false);
        }
        finally
        {
            if (!process.HasExited) process.Kill();
        }
    }

    private static async Task<string> ReadBoundedAsync(StreamReader reader, CancellationToken token)
    {
        var output = new StringBuilder();
        var buffer = new char[4096];
        int count;
        while ((count = await reader.ReadAsync(buffer.AsMemory(), token).ConfigureAwait(false)) != 0)
        {
            if (output.Length + count > 256 * 1024) throw new InvalidDataException("Runtime output exceeded its budget.");
            output.Append(buffer, 0, count);
        }
        return output.ToString();
    }
}
