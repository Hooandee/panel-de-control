using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.GameBar;

public sealed class VolumeControlClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Control";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(5);

    public Task<VolumeControlResponse> GetAsync()
    {
        return SendAsync(VolumeControlRequest.Get());
    }

    public Task<VolumeControlResponse> SetAsync(double requestedLevel)
    {
        return SendAsync(VolumeControlRequest.Set(requestedLevel));
    }

    private static async Task<VolumeControlResponse> SendAsync(
        VolumeControlRequest request)
    {
        var attempt = await TrySendAsync(request);
        if (attempt.Response is not null)
        {
            return attempt.Response;
        }

        if (!attempt.RequestSent)
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
            attempt.RequestSent
                ? "control_response_unavailable"
                : "broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(
        VolumeControlRequest request)
    {
        var requestSent = false;
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

            await writer.WriteLineAsync(
                VolumeControlWireCodec.SerializeRequest(request));
            requestSent = true;

            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(ResponseTimeout)) != readTask)
            {
                return new TransportAttempt(null, requestSent);
            }

            var payload = await readTask;
            if (string.IsNullOrWhiteSpace(payload))
            {
                return new TransportAttempt(null, requestSent);
            }

            return new TransportAttempt(
                VolumeControlWireCodec.DeserializeResponse(payload),
                requestSent);
        }
        catch
        {
            return new TransportAttempt(null, requestSent);
        }
    }

    private static VolumeControlResponse TransportFailure(
        VolumeControlRequest request,
        string errorCode)
    {
        return request.Operation == VolumeControlOperation.Set
            ? VolumeControlResponse.Unverifiable(
                request.RequestedLevel!.Value,
                null,
                errorCode)
            : VolumeControlResponse.Fault(errorCode);
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(
            VolumeControlResponse? response,
            bool requestSent)
        {
            Response = response;
            RequestSent = requestSent;
        }

        public VolumeControlResponse? Response { get; }

        public bool RequestSent { get; }
    }
}
