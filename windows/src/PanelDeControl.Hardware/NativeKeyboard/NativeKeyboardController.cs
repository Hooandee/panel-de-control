using System.Text.Json;
using System.Text.RegularExpressions;
using PanelDeControl.Core.NativeKeyboard;

namespace PanelDeControl.Hardware.NativeKeyboard;

public interface INativeKeyboardHost
{
    bool Available { get; }
    Task RunAsync(Action<string> onReceipt, CancellationToken token);
    Task RequestStopAsync(CancellationToken token);
}

public sealed class NativeKeyboardController(
    INativeKeyboardHost host, TimeSpan? receiptTimeout = null, TimeSpan? stopTimeout = null) : IAsyncDisposable
{
    private readonly SemaphoreSlim gate = new(1, 1);
    private readonly object sync = new();
    private NativeKeyboardStatus status = new();
    private CancellationTokenSource? lifetime;
    private Task? running;
    private int generation;
    private bool disposed;
    public NativeKeyboardStatus Status => Volatile.Read(ref status);

    public async Task<NativeKeyboardStatus> SetEnabledAsync(bool enabled, CancellationToken token)
    {
        await gate.WaitAsync(token).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (!enabled) return await StopAsync().ConfigureAwait(false);
            lock (sync)
            {
                if (running is { IsCompleted: false }) return Status;
                if (Status.Status == "restore_unconfirmed") return Status;
                if (!host.Available) return Publish(Failure(true, "runtime_missing", "runtime_missing"));
                lifetime?.Dispose();
                lifetime = new CancellationTokenSource(receiptTimeout ?? TimeSpan.FromSeconds(15));
                var current = ++generation;
                var cancellation = lifetime;
                Publish(new NativeKeyboardStatus { Requested = true, Status = "applying" });
                running = Task.Run(() => MonitorAsync(current, cancellation));
                return Status;
            }
        }
        finally { gate.Release(); }
    }

    private async Task MonitorAsync(int current, CancellationTokenSource cancellation)
    {
        try
        {
            await host.RunAsync(output => Receive(current, output, cancellation), cancellation.Token).ConfigureAwait(false);
            lock (sync)
            {
                if (current != generation || Status.Status is "connection_failed" or "restore_unconfirmed" or "unsupported" or "runtime_missing" || (!Status.Requested && Status.Status == "disabled")) return;
                Publish(Failure(Status.Requested, Status.Requested ? "connection_failed" : "restore_unconfirmed", "runtime_exited"));
            }
        }
        catch (Exception exception) when (exception is OperationCanceledException or IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception or InvalidOperationException or InvalidDataException)
        {
            lock (sync)
            {
                if (current != generation || Status.Status is "connection_failed" or "restore_unconfirmed" or "unsupported" or "runtime_missing" || (!Status.Requested && Status.Status == "disabled")) return;
                var error = exception is OperationCanceledException ? "runtime_timeout" : "runtime_failed";
                Publish(Failure(Status.Requested, Status.Requested ? "connection_failed" : "restore_unconfirmed", error));
            }
        }
    }

    private void Receive(int current, string output, CancellationTokenSource cancellation)
    {
        lock (sync)
        {
            if (current != generation || cancellation.IsCancellationRequested) return;
            try
            {
                var value = Parse(output);
                value.Requested = Status.Requested;
                if (!value.Requested && value.Status is not ("disabled" or "restoring" or "connection_failed")) return;
                if (value.Requested && value.Status == "disabled") throw new InvalidDataException();
                if (!value.Requested && value.Status == "connection_failed") value.Status = "restore_unconfirmed";
                cancellation.CancelAfter(receiptTimeout ?? TimeSpan.FromSeconds(6));
                Publish(value);
            }
            catch (Exception exception) when (exception is JsonException or InvalidDataException or InvalidOperationException or KeyNotFoundException or FormatException or OverflowException)
            {
                Publish(Failure(Status.Requested, Status.Requested ? "connection_failed" : "restore_unconfirmed", "invalid_runtime_response"));
                cancellation.Cancel();
            }
        }
    }

    private async Task<NativeKeyboardStatus> StopAsync()
    {
        Task? task;
        lock (sync)
        {
            task = running;
            if (task is null)
                return Status.Status == "restore_unconfirmed" ? Status : Publish(new NativeKeyboardStatus());
            if (task.IsCompleted)
            {
                running = null;
                if (Status.Status is "unsupported" or "runtime_missing" && !Status.Connected && Status.StyledKeys == 0)
                    return Publish(new NativeKeyboardStatus());
                return Publish(Failure(false, "restore_unconfirmed", "restore_receipt_missing"));
            }
            Publish(new NativeKeyboardStatus { Status = "restoring" });
        }
        using var deadline = new CancellationTokenSource(stopTimeout ?? TimeSpan.FromSeconds(6));
        try
        {
            await host.RequestStopAsync(deadline.Token).WaitAsync(deadline.Token).ConfigureAwait(false);
            await task.WaitAsync(deadline.Token).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is OperationCanceledException or IOException or InvalidOperationException)
        {
        }
        lock (sync)
        {
            generation++;
            lifetime?.Cancel();
            running = null;
            if (Status.Status != "disabled") Publish(Failure(false, "restore_unconfirmed", "restore_receipt_missing"));
            return Status;
        }
    }

    public async ValueTask DisposeAsync()
    {
        await gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (disposed) return;
            await StopAsync().ConfigureAwait(false);
            disposed = true;
            lifetime?.Cancel();
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
            observedElements = value.ObservedElements, styledKeys = value.StyledKeys,
            restoredKeys = value.RestoredKeys, keyCount = value.KeyCount, hresult = value.HResult,
            nodes = Array.Empty<object>(),
        });
        var previous = Status;
        Volatile.Write(ref status, value);
        if (previous.Status != value.Status || previous.ErrorCode != value.ErrorCode || previous.ProcessId != value.ProcessId || previous.StyledKeys != value.StyledKeys)
            CompanionLog.Write("native_keyboard.state", $"requested={value.Requested} status={value.Status} error={value.ErrorCode} build={value.WindowsBuild} arch={value.Architecture} pid={value.ProcessId} connected={value.Connected} styled={value.StyledKeys} restored={value.RestoredKeys} hresult={value.HResult}");
        return value;
    }

    private static NativeKeyboardStatus Failure(bool requested, string state, string code) => new() { Requested = requested, Status = state, ErrorCode = code };
    private static readonly HashSet<string> Errors = new(StringComparer.Ordinal)
    {
        "probe_build_unverified", "styles_active", "styles_pending", "keyboard_not_visible", "styles_restoring", "styles_restored", "restore_unconfirmed", "selectors_unverified", "invalid_command", "unsupported_windows_or_architecture", "ambiguous_target",
        "keyboard_not_running", "target_not_authorized", "xaml_framework_not_observed", "discovery_busy",
        "runtime_path_invalid", "tap_missing", "target_token_unavailable", "ipc_security_failed", "ipc_create_failed",
        "ipc_connect_failed", "xaml_diagnostics_missing", "xaml_attach_failed", "tap_receipt_timeout",
        "restore_failed", "style_failed", "keyboard_schema_unverified", "native_runtime_busy", "receipt_sender_invalid", "receipt_invalid", "receipt_incomplete", "xaml_subscribe_failed", "xaml_unsubscribe_failed",
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
            StyledKeys = root.GetProperty("styledKeys").GetInt32(),
            RestoredKeys = root.GetProperty("restoredKeys").GetInt32(),
            KeyCount = root.GetProperty("keyCount").GetInt32(),
            HResult = root.GetProperty("hresult").GetInt32(),
            PendingKeys = root.GetProperty("pendingKeys").GetInt32(),
        };
        if (value.Status is not ("applying" or "applied" or "waiting_for_keyboard" or "restoring" or "disabled" or "runtime_missing" or "unsupported" or "connection_failed") ||
            (value.ErrorCode is not null && !Errors.Contains(value.ErrorCode)) || value.WindowsBuild < 0 || value.ProcessId < 0 ||
            value.Architecture is not ("x64" or "arm64" or "x86" or "unknown") || value.ObservedElements is < 0 or > 512 ||
            value.PendingKeys is < 0 or > 256 || value.StyledKeys is < 0 or > 256 || value.RestoredKeys < 0 || value.KeyCount is < 0 or > 256 ||
            (value.Connected && value.ProcessId == 0) ||
            (value.Status == "applied" && (!value.Connected || value.WindowsBuild != 26300 || value.Architecture != "x64" || value.StyledKeys == 0 || value.StyledKeys != value.KeyCount || value.PendingKeys != 0 || value.HResult != 0 || value.ErrorCode != "styles_active")) ||
            (value.Status == "disabled" && (value.StyledKeys != 0 || value.PendingKeys != 0 || value.KeyCount != 0 || value.HResult != 0 || value.ErrorCode != "styles_restored")))
            throw new InvalidDataException();
        if (value.Status == "disabled") value.Connected = false;
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
        var states = root.GetProperty("stateCatalog");
        if (states.ValueKind != JsonValueKind.Array || states.GetArrayLength() > 64) throw new InvalidDataException();
        var stateCatalog = new List<string>();
        foreach (var state in states.EnumerateArray())
        {
            var name = state.GetString() ?? "";
            if (name.Length is 0 or > 127 || !Regex.IsMatch(name, @"\A[A-Za-z0-9._:/-]+\z")) throw new InvalidDataException();
            stateCatalog.Add(name);
        }
        value.Diagnostics = JsonSerializer.Serialize(new
        {
            status = value.Status, errorCode = value.ErrorCode, windowsBuild = value.WindowsBuild,
            architecture = value.Architecture, processId = value.ProcessId, connected = value.Connected,
            observedElements = value.ObservedElements, hresult = value.HResult,
            styledKeys = value.StyledKeys, restoredKeys = value.RestoredKeys, keyCount = value.KeyCount,
            pendingKeys = value.PendingKeys, stateCatalog,
            truncated = root.TryGetProperty("truncated", out var truncated) && truncated.GetBoolean(), nodes,
        });
        return value;
    }
}
