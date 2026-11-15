using System.Text.Json;
using System.Text.RegularExpressions;
using PanelDeControl.Core.NativeKeyboard;

namespace PanelDeControl.Hardware.NativeKeyboard;

public interface INativeKeyboardHost
{
    bool Available { get; }
    Task<string> DiscoverAsync(CancellationToken token);
}

public sealed class NativeKeyboardController(INativeKeyboardHost host, TimeSpan? timeout = null)
{
    private readonly SemaphoreSlim gate = new(1, 1);
    private NativeKeyboardStatus status = new();
    public NativeKeyboardStatus Status => Volatile.Read(ref status);

    public async Task<NativeKeyboardStatus> SetEnabledAsync(bool enabled, CancellationToken token)
    {
        await gate.WaitAsync(token).ConfigureAwait(false);
        try
        {
            if (!enabled) return Publish(new NativeKeyboardStatus());
            if (!host.Available) return Publish(Failure("runtime_missing", "runtime_missing"));
            Publish(new NativeKeyboardStatus { Requested = true, Status = "discovering" });
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(timeout ?? TimeSpan.FromSeconds(15));
            try
            {
                var output = await host.DiscoverAsync(deadline.Token).WaitAsync(deadline.Token).ConfigureAwait(false);
                return Publish(Parse(output));
            }
            catch (OperationCanceledException)
            {
                return Publish(Failure("connection_failed", token.IsCancellationRequested ? "runtime_cancelled" : "runtime_timeout"));
            }
            catch (Exception exception) when (exception is JsonException or InvalidDataException or InvalidOperationException or KeyNotFoundException or FormatException or OverflowException)
            {
                return Publish(Failure("connection_failed", "invalid_runtime_response"));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception)
            {
                return Publish(Failure("connection_failed", "runtime_start_failed"));
            }
        }
        finally { gate.Release(); }
    }

    private NativeKeyboardStatus Publish(NativeKeyboardStatus value)
    {
        value.Diagnostics ??= JsonSerializer.Serialize(new
        {
            requested = value.Requested, status = value.Status, errorCode = value.ErrorCode,
            windowsBuild = value.WindowsBuild, architecture = value.Architecture,
            processId = value.ProcessId, connected = value.Connected,
            observedElements = value.ObservedElements, nodes = Array.Empty<object>(),
        });
        Volatile.Write(ref status, value);
        CompanionLog.Write("native_keyboard.state", $"requested={value.Requested} status={value.Status} error={value.ErrorCode} build={value.WindowsBuild} arch={value.Architecture} pid={value.ProcessId} connected={value.Connected} elements={value.ObservedElements}");
        return value;
    }

    private static NativeKeyboardStatus Failure(string state, string code) => new() { Requested = true, Status = state, ErrorCode = code };

    private static readonly HashSet<string> Errors = new(StringComparer.Ordinal)
    {
        "selectors_unverified", "invalid_command", "unsupported_windows_or_architecture", "ambiguous_target",
        "keyboard_not_running", "target_not_authorized", "xaml_framework_not_observed", "discovery_busy",
        "runtime_path_invalid", "tap_missing", "target_token_unavailable", "ipc_security_failed", "ipc_create_failed",
        "ipc_connect_failed", "xaml_diagnostics_missing", "xaml_attach_failed", "tap_receipt_timeout",
        "receipt_sender_invalid", "receipt_invalid", "receipt_incomplete", "xaml_subscribe_failed", "xaml_unsubscribe_failed",
    };

    private static NativeKeyboardStatus Parse(string output)
    {
        if (output.Length > 256 * 1024) throw new InvalidDataException();
        using var document = JsonDocument.Parse(output, new JsonDocumentOptions { MaxDepth = 8 });
        var root = document.RootElement;
        var value = new NativeKeyboardStatus
        {
            Requested = true,
            Status = root.GetProperty("status").GetString() ?? "",
            ErrorCode = root.GetProperty("errorCode").GetString(),
            Connected = root.GetProperty("connected").GetBoolean(),
            WindowsBuild = root.GetProperty("windowsBuild").GetInt32(),
            Architecture = root.GetProperty("architecture").GetString() ?? "",
            ProcessId = root.GetProperty("processId").GetInt32(),
            ObservedElements = root.GetProperty("observedElements").GetInt32(),
        };
        if (value.Status is not ("discovery_required" or "runtime_missing" or "unsupported" or "connection_failed") ||
            value.ErrorCode is null || !Errors.Contains(value.ErrorCode) || value.WindowsBuild < 0 || value.ProcessId < 0 ||
            value.Architecture is not ("x64" or "arm64" or "x86" or "unknown") || value.ObservedElements is < 0 or > 512 ||
            (value.Status == "discovery_required" && (!value.Connected || value.WindowsBuild < 22000 || value.ProcessId == 0 || value.ErrorCode != "selectors_unverified")))
            throw new InvalidDataException();
        var nodes = new List<object>();
        var elements = root.GetProperty("nodes");
        {
            if (elements.ValueKind != JsonValueKind.Array || elements.GetArrayLength() != value.ObservedElements) throw new InvalidDataException();
            foreach (var node in elements.EnumerateArray())
            {
                var type = node.GetProperty("type").GetString() ?? "";
                if (type.Length is 0 or > 127 || !Regex.IsMatch(type, @"\A[A-Za-z0-9._`]+\z")) throw new InvalidDataException();
                nodes.Add(new { id = node.GetProperty("id").GetUInt64(), parent = node.GetProperty("parent").GetUInt64(), type });
            }
        }
        var hresult = root.TryGetProperty("hresult", out var hr) ? hr.GetInt32() : 0;
        value.Diagnostics = JsonSerializer.Serialize(new
        {
            status = value.Status, errorCode = value.ErrorCode, windowsBuild = value.WindowsBuild,
            architecture = value.Architecture, processId = value.ProcessId, connected = value.Connected,
            observedElements = value.ObservedElements, hresult,
            truncated = root.TryGetProperty("truncated", out var truncated) && truncated.GetBoolean(), nodes,
        });
        return value;
    }
}
