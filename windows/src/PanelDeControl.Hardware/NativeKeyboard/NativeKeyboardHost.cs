using System.Diagnostics;
using PanelDeControl.Core.NativeKeyboard;
using System.Text;

namespace PanelDeControl.Hardware.NativeKeyboard;

public sealed class NativeKeyboardHost : INativeKeyboardHost
{
    private const int MaximumLineLength = 256 * 1024;
    private readonly string executable = Path.Combine(AppContext.BaseDirectory, "NativeKeyboard", "PanelDeControl.KeyboardHost.exe");
    private Process? active;
    private TaskCompletionSource<Process> ready = NewReady();
    private static TaskCompletionSource<Process> NewReady() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool Available => File.Exists(executable) && File.Exists(Path.Combine(Path.GetDirectoryName(executable)!, "PanelDeControl.KeyboardTap.dll"));

    public Task RunAsync(string themeId, Action<string> onReceipt, CancellationToken token) =>
        RunCommandAsync("serve", themeId, onReceipt, token);

    public Task RestoreAsync(string themeId, Action<string> onReceipt, CancellationToken token) =>
        RunCommandAsync("restore", themeId, onReceipt, token);

    private async Task RunCommandAsync(string command, string themeId, Action<string> onReceipt, CancellationToken token)
    {
        if (!NativeKeyboardThemes.IsValid(themeId)) throw new ArgumentException("Unknown keyboard theme.", nameof(themeId));
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo(executable)
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = Path.GetDirectoryName(executable)!,
            },
        };
        process.StartInfo.ArgumentList.Add(command);
        process.StartInfo.ArgumentList.Add(themeId);
        var started = Volatile.Read(ref ready);
        var launched = false;
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(token);
        Task stdout = Task.CompletedTask, stderr = Task.CompletedTask;
        try
        {
            if (!process.Start()) throw new IOException("Runtime did not start.");
            launched = true;
            Volatile.Write(ref active, process);
            started.TrySetResult(process);
            stdout = ReadLinesAsync(process.StandardOutput, onReceipt, lifetime);
            stderr = ReadLinesAsync(process.StandardError, _ => { }, lifetime);
            await Task.WhenAll(stdout, stderr, process.WaitForExitAsync(lifetime.Token)).ConfigureAwait(false);
            if (process.ExitCode != 0) throw new IOException("Runtime exited unsuccessfully.");
        }
        finally
        {
            started.TrySetCanceled();
            Interlocked.CompareExchange(ref active, null, process);
            lifetime.Cancel();
            if (launched)
            {
                try { if (!process.HasExited) process.Kill(); }
                finally { await process.WaitForExitAsync().ConfigureAwait(false); }
            }
            try { await Task.WhenAll(stdout, stderr).ConfigureAwait(false); }
            catch (Exception exception) when (exception is OperationCanceledException or IOException or InvalidDataException) { }
            Interlocked.CompareExchange(ref ready, NewReady(), started);
        }
    }

    public async Task RequestStopAsync(CancellationToken token)
    {
        var process = Volatile.Read(ref active) ?? await Volatile.Read(ref ready).Task.WaitAsync(token).ConfigureAwait(false);
        await process.StandardInput.WriteLineAsync("stop".AsMemory(), token).ConfigureAwait(false);
        await process.StandardInput.FlushAsync(token).ConfigureAwait(false);
    }

    private static async Task ReadLinesAsync(StreamReader reader, Action<string> receive, CancellationTokenSource lifetime)
    {
        try
        {
            var line = new StringBuilder();
            var buffer = new char[4096];
            int count;
            while ((count = await reader.ReadAsync(buffer.AsMemory(), lifetime.Token).ConfigureAwait(false)) != 0)
            {
                for (var index = 0; index < count; index++)
                {
                    var character = buffer[index];
                    if (character == '\n')
                    {
                        if (line.Length == 0) throw new InvalidDataException("Empty runtime receipt.");
                        receive(line.ToString());
                        line.Clear();
                    }
                    else if (character != '\r')
                    {
                        if (line.Length == MaximumLineLength) throw new InvalidDataException("Runtime line exceeded its budget.");
                        line.Append(character);
                    }
                }
            }
            if (line.Length != 0) throw new InvalidDataException("Incomplete runtime receipt.");
        }
        catch
        {
            lifetime.Cancel();
            throw;
        }
    }
}
