using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.GameBar;

public sealed class BrightnessControlClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Display";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(6);

    public Task<BrightnessControlResponse> GetAsync()
    {
        return SendAsync(BrightnessControlRequest.Get());
    }

    public Task<BrightnessControlResponse> SetAsync(int requestedPercentage)
    {
        return SendAsync(BrightnessControlRequest.Set(requestedPercentage));
    }

    private static async Task<BrightnessControlResponse> SendAsync(
        BrightnessControlRequest request)
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
                    "brightness_broker_launch_failed");
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
                ? "brightness_response_unavailable"
                : "brightness_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(
        BrightnessControlRequest request)
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
                BrightnessControlWireCodec.SerializeRequest(request));

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
                BrightnessControlWireCodec.DeserializeResponse(payload),
                requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static BrightnessControlResponse TransportFailure(
        BrightnessControlRequest request,
        string errorCode)
    {
        return request.Operation == BrightnessControlOperation.Set
            ? BrightnessControlResponse.Unverifiable(
                request.RequestedPercentage!.Value,
                null,
                errorCode)
            : BrightnessControlResponse.Fault(errorCode);
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(
            BrightnessControlResponse? response,
            bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public BrightnessControlResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
