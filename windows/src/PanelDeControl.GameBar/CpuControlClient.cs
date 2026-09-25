using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.GameBar;

public sealed class CpuControlClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Cpu";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(6);

    public Task<CpuControlResponse> GetAsync()
    {
        return SendAsync(CpuControlRequest.Get());
    }

    public Task<CpuControlResponse> SetBoostAsync(bool enabled)
    {
        return SendAsync(CpuControlRequest.SetBoost(enabled));
    }

    public Task<CpuControlResponse> SetMaximumStateAsync(int percent)
    {
        return SendAsync(CpuControlRequest.SetMaximumState(percent));
    }

    private static async Task<CpuControlResponse> SendAsync(
        CpuControlRequest request)
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
                    "cpu_broker_launch_failed");
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
                ? "cpu_response_unavailable"
                : "cpu_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(
        CpuControlRequest request)
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
                CpuControlWireCodec.SerializeRequest(request));

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
                CpuControlWireCodec.DeserializeResponse(payload),
                requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static CpuControlResponse TransportFailure(
        CpuControlRequest request,
        string errorCode)
    {
        return request.Operation == CpuControlOperation.Get
            ? CpuControlResponse.Fault(errorCode)
            : CpuControlResponse.Unverifiable(null, null, errorCode);
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(
            CpuControlResponse? response,
            bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public CpuControlResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
