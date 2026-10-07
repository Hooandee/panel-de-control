using System.Collections.Concurrent;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace PanelDeControl.Hardware.Themes;

public sealed record DevToolsTarget(string Id, string Title, string Url, string Type, string WebSocketUrl);

public sealed class CdpException : Exception
{
    public CdpException(string message)
        : base(message)
    {
    }
}

public interface ICdpSession : IAsyncDisposable
{
    bool IsOpen { get; }

    Task<JsonElement> EvaluateAsync(string expression, CancellationToken cancellationToken);
}

public interface ISteamDevTools
{
    Task<IReadOnlyList<DevToolsTarget>?> ListTargetsAsync(CancellationToken cancellationToken);

    Task<ICdpSession> ConnectAsync(DevToolsTarget target, CancellationToken cancellationToken);
}

/// <summary>
/// Steam's CEF remote debugging endpoint. It only exists while Steam runs with
/// <c>.cef-enable-remote-debugging</c> and only listens on the loopback interface.
/// </summary>
public sealed class SteamDevTools : ISteamDevTools, IDisposable
{
    public static readonly Uri DefaultEndpoint = new("http://127.0.0.1:8080/");

    private readonly Uri endpoint;
    private readonly HttpClient http;

    public SteamDevTools(Uri? endpoint = null)
    {
        this.endpoint = endpoint ?? DefaultEndpoint;
        http = new HttpClient(new SocketsHttpHandler { UseProxy = false, ConnectTimeout = TimeSpan.FromSeconds(1) })
        {
            Timeout = TimeSpan.FromSeconds(2),
        };
    }

    public async Task<IReadOnlyList<DevToolsTarget>?> ListTargetsAsync(CancellationToken cancellationToken)
    {
        try
        {
            var json = await http.GetByteArrayAsync(new Uri(endpoint, "json"), cancellationToken).ConfigureAwait(false);
            using var document = JsonDocument.Parse(json);
            return document.RootElement.EnumerateArray()
                .Select(target => new DevToolsTarget(
                    target.GetProperty("id").GetString() ?? string.Empty,
                    target.TryGetProperty("title", out var title) ? title.GetString() ?? string.Empty : string.Empty,
                    target.TryGetProperty("url", out var url) ? url.GetString() ?? string.Empty : string.Empty,
                    target.TryGetProperty("type", out var type) ? type.GetString() ?? string.Empty : string.Empty,
                    target.TryGetProperty("webSocketDebuggerUrl", out var socket) ? socket.GetString() ?? string.Empty : string.Empty))
                .Where(target => target.Id.Length > 0 && IsLoopbackSocket(target.WebSocketUrl))
                .ToArray();
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException or KeyNotFoundException)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                throw;
            }

            return null;
        }
    }

    public async Task<ICdpSession> ConnectAsync(DevToolsTarget target, CancellationToken cancellationToken)
    {
        var socket = new ClientWebSocket();
        socket.Options.Proxy = null;
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(3));
            await socket.ConnectAsync(new Uri(target.WebSocketUrl), timeout.Token).ConfigureAwait(false);
            return new CdpSession(socket);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }

    public void Dispose() => http.Dispose();

    private static bool IsLoopbackSocket(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var uri)
        && uri.Scheme == "ws"
        && uri.IsLoopback;

    private sealed class CdpSession : ICdpSession
    {
        private const int MaximumMessageBytes = 16 * 1024 * 1024;

        private readonly ClientWebSocket socket;
        private readonly ConcurrentDictionary<int, TaskCompletionSource<JsonElement>> pending = new();
        private readonly SemaphoreSlim sendGate = new(1, 1);
        private readonly CancellationTokenSource lifetime = new();
        private readonly Task receiveLoop;
        private int nextId;

        public CdpSession(ClientWebSocket socket)
        {
            this.socket = socket;
            receiveLoop = Task.Run(ReceiveAsync);
        }

        public bool IsOpen => socket.State == WebSocketState.Open && !receiveLoop.IsCompleted;

        public async Task<JsonElement> EvaluateAsync(string expression, CancellationToken cancellationToken)
        {
            var id = Interlocked.Increment(ref nextId);
            var completion = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
            pending[id] = completion;
            try
            {
                var message = JsonSerializer.SerializeToUtf8Bytes(new
                {
                    id,
                    method = "Runtime.evaluate",
                    @params = new { expression, returnByValue = true, awaitPromise = true },
                });
                await sendGate.WaitAsync(cancellationToken).ConfigureAwait(false);
                try
                {
                    await socket.SendAsync(message, WebSocketMessageType.Text, true, cancellationToken).ConfigureAwait(false);
                }
                finally
                {
                    sendGate.Release();
                }

                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                timeout.CancelAfter(TimeSpan.FromSeconds(5));
                using var registration = timeout.Token.Register(() => completion.TrySetCanceled());
                var response = await completion.Task.ConfigureAwait(false);
                if (response.TryGetProperty("error", out var error))
                {
                    throw new CdpException(error.ToString());
                }

                var result = response.GetProperty("result");
                if (result.TryGetProperty("exceptionDetails", out var exception))
                {
                    throw new CdpException(exception.TryGetProperty("text", out var text) ? text.ToString() : "evaluation failed");
                }

                return result.GetProperty("result").TryGetProperty("value", out var value) ? value.Clone() : default;
            }
            finally
            {
                pending.TryRemove(id, out _);
            }
        }

        public async ValueTask DisposeAsync()
        {
            lifetime.Cancel();
            try
            {
                if (socket.State == WebSocketState.Open)
                {
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(1));
                    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, null, timeout.Token).ConfigureAwait(false);
                }
            }
            catch (Exception exception) when (exception is WebSocketException or OperationCanceledException or ObjectDisposedException)
            {
            }

            socket.Dispose();
            foreach (var waiting in pending.Values)
            {
                waiting.TrySetCanceled();
            }

            sendGate.Dispose();
            lifetime.Dispose();
        }

        private async Task ReceiveAsync()
        {
            var buffer = new byte[64 * 1024];
            var message = new MemoryStream();
            try
            {
                while (!lifetime.IsCancellationRequested && socket.State == WebSocketState.Open)
                {
                    var received = await socket.ReceiveAsync(buffer, lifetime.Token).ConfigureAwait(false);
                    if (received.MessageType == WebSocketMessageType.Close)
                    {
                        break;
                    }

                    message.Write(buffer, 0, received.Count);
                    if (message.Length > MaximumMessageBytes)
                    {
                        break;
                    }

                    if (!received.EndOfMessage)
                    {
                        continue;
                    }

                    Dispatch(message.ToArray());
                    message.SetLength(0);
                }
            }
            catch (Exception exception) when (exception is WebSocketException or OperationCanceledException or ObjectDisposedException)
            {
            }
            finally
            {
                foreach (var waiting in pending.Values)
                {
                    waiting.TrySetException(new CdpException("DevTools connection closed"));
                }
            }
        }

        private void Dispatch(byte[] payload)
        {
            try
            {
                using var document = JsonDocument.Parse(payload);
                if (document.RootElement.TryGetProperty("id", out var id)
                    && id.TryGetInt32(out var value)
                    && pending.TryGetValue(value, out var completion))
                {
                    completion.TrySetResult(document.RootElement.Clone());
                }
            }
            catch (JsonException)
            {
            }
        }
    }
}
