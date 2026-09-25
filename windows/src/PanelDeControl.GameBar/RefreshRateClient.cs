using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.GameBar;

public sealed class RefreshRateClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Refresh";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(6);

    public Task<RefreshRateResponse> GetAsync()
    {
        return SendAsync(RefreshRateRequest.Get());
    }

    public Task<RefreshRateResponse> SetAsync(int requestedHertz)
    {
        return SendAsync(RefreshRateRequest.Set(requestedHertz));
    }

    private static async Task<RefreshRateResponse> SendAsync(
        RefreshRateRequest request)
    {
        var attempt = await TrySendAsync(request);
        if (attempt.Response is not null)
        {
            return attempt.Response;
        }

        if (!attempt.RequestWriteStarted)
        {
            try
            {
                await HardwareBrokerLauncher.EnsureStartedAsync();
            }
            catch
            {
                return TransportFailure(
                    request,
                    "refresh_broker_launch_failed");
            }

            attempt = await TrySendAsync(request);
            if (attempt.Response is not null)
            {
                return attempt.Response;
            }
        }

        return TransportFailure(
            request,
            attempt.RequestWriteStarted
                ? "refresh_response_unavailable"
                : "refresh_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(
        RefreshRateRequest request)
    {
        var requestWriteStarted = false;
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

            requestWriteStarted = true;
            await writer.WriteLineAsync(
                RefreshRateWireCodec.SerializeRequest(request));

            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(ResponseTimeout)) != readTask)
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            var payload = await readTask;
            if (string.IsNullOrWhiteSpace(payload))
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            return new TransportAttempt(
                RefreshRateWireCodec.DeserializeResponse(payload),
                requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static RefreshRateResponse TransportFailure(
        RefreshRateRequest request,
        string errorCode)
    {
        return request.Operation == RefreshRateOperation.Set
            ? RefreshRateResponse.Unverifiable(
                request.RequestedHertz!.Value,
                null,
                null,
                errorCode)
            : RefreshRateResponse.Fault(errorCode);
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(
            RefreshRateResponse? response,
            bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public RefreshRateResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
