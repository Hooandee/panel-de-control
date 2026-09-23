using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.GameBar;

public sealed class TdpControlClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Tdp";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(9);

    public Task<TdpControlResponse> GetAsync()
    {
        return SendAsync(TdpControlRequest.Get());
    }

    public Task<TdpControlResponse> EnableExperimentalAsync()
    {
        return SendAsync(TdpControlRequest.EnableExperimental());
    }

    public Task<TdpControlResponse> DisableExperimentalAsync()
    {
        return SendAsync(TdpControlRequest.DisableExperimental());
    }

    public Task<TdpControlResponse> SetAsync(int requestedWatts)
    {
        return SendAsync(TdpControlRequest.Set(requestedWatts));
    }

    private static async Task<TdpControlResponse> SendAsync(
        TdpControlRequest request)
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
                return TransportFailure(request, "broker_launch_failed");
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
                ? "tdp_response_unavailable"
                : "broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(
        TdpControlRequest request)
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
                TdpControlWireCodec.SerializeRequest(request));
            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(ResponseTimeout)) !=
                readTask)
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            var payload = await readTask;
            return string.IsNullOrWhiteSpace(payload)
                ? new TransportAttempt(null, requestWriteStarted)
                : new TransportAttempt(
                    TdpControlWireCodec.DeserializeResponse(payload),
                    requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static TdpControlResponse TransportFailure(
        TdpControlRequest request,
        string errorCode)
    {
        return request.Operation == TdpControlOperation.Set
            ? TdpControlResponse.Indeterminate(
                false,
                request.RequestedWatts!.Value,
                errorCode,
                experimentalStateKnown: false)
            : TdpControlResponse.Fault(
                false,
                errorCode,
                experimentalStateKnown: false);
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(
            TdpControlResponse? response,
            bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public TdpControlResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
