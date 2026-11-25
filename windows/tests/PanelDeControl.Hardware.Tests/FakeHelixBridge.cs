using System.Text.Json.Nodes;
using PanelDeControl.Hardware.Upscalers;

namespace PanelDeControl.Hardware.Tests;

public sealed record HelixCall(string Executable, string[] Arguments, string WorkingDirectory, TimeSpan Timeout);

/// <summary>
/// Stands in for Python running HelixSR's bridge: <c>install --way fsr</c> swaps the game's amd_fidelityfx_dx12.dll for a
/// HelixSR build and keeps the game's file beside it, <c>remove</c> puts it back, as the real bridge does.
/// </summary>
public sealed class FakeHelixBridge : IHelixProcess
{
    public const string Drop = "HLX-FSR-4 drop-in";
    public const string Library = "amd_fidelityfx_dx12.dll";
    public const string Backup = "amd_fidelityfx_dx12.original.dll";

    public List<HelixCall> Calls { get; } = new();

    /// <summary>Thrown by the next call instead of answering.</summary>
    public Exception? Failure { get; set; }

    /// <summary>Replaces the answer to every call.</summary>
    public Func<string[], HelixProcessResult>? Answer { get; set; }

    public Action<string[]>? Observe { get; set; }

    public Task<HelixProcessResult> RunAsync(string executable, IReadOnlyList<string> arguments, string workingDirectory, TimeSpan timeout, CancellationToken cancel)
    {
        var line = arguments.ToArray();
        Calls.Add(new HelixCall(executable, line, workingDirectory, timeout));
        Observe?.Invoke(line);
        if (Failure is { } failure)
        {
            return Task.FromException<HelixProcessResult>(failure);
        }

        return Task.FromResult(Answer is not null ? Answer(line) : Simulate(line));
    }

    public static HelixProcessResult Ok(string game, string? logName = "helixsr.log")
    {
        var folder = Path.Combine(game, "Binaries", "Win64");
        return new HelixProcessResult(0, "starting\r\n" + new JsonObject
        {
            ["ok"] = true,
            ["game"] = new JsonObject { ["exe_folder"] = folder, ["log_path"] = Path.Combine(folder, logName ?? "helixsr.log") },
        }.ToJsonString() + "\r\n", string.Empty);
    }

    public static HelixProcessResult Fail(string error) =>
        new(1, new JsonObject { ["ok"] = false, ["error"] = error }.ToJsonString(), string.Empty);

    private static HelixProcessResult Simulate(string[] line)
    {
        var command = line[4];
        var game = line[Array.IndexOf(line, "--game") + 1];
        var folder = Path.Combine(game, "Binaries", "Win64");
        var library = Path.Combine(folder, Library);
        var backup = Path.Combine(folder, Backup);
        var record = Path.Combine(folder, "helixsr-install.json");
        if (command == "install")
        {
            if (File.Exists(library) && !File.Exists(backup))
            {
                File.Move(library, backup);
            }

            File.WriteAllText(library, Drop);
            File.WriteAllText(record, "{\"files\": [\"" + Library + "\"]}");
            return Ok(game);
        }

        if (!File.Exists(record) || File.ReadAllText(library) != Drop)
        {
            return Fail("HelixSR is not installed in " + library);
        }

        File.Delete(library);
        File.Move(backup, library);
        File.Delete(record);
        return Ok(game);
    }
}
