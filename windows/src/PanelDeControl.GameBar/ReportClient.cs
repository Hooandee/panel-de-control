using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Reports;

namespace PanelDeControl.GameBar;

public sealed class ReportClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Reports";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);

    // Collecting the drivers and the upload together stay well under this; the companion never cuts a
    // report short, so waiting longer only avoids showing a failure for a report that did arrive.
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(120);

    public async Task<ReportResponse> SendAsync(ReportRequest request)
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
                return ReportResponse.Rejected("report_broker_launch_failed");
            }

            attempt = await TrySendAsync(request);
            if (attempt.Response is not null)
            {
                return attempt.Response;
            }
        }

        return ReportResponse.Rejected(attempt.RequestWriteStarted ? "report_response_unavailable" : "report_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(ReportRequest request)
    {
        var requestWriteStarted = false;
        try
        {
            using var pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync((int)ConnectTimeout.TotalMilliseconds);
            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 1024, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 1024, leaveOpen: true) { AutoFlush = true };

            requestWriteStarted = true;
            await writer.WriteLineAsync(ReportWireCodec.SerializeRequest(request));

            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(ResponseTimeout)) != readTask)
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            var payload = await readTask;
            return string.IsNullOrWhiteSpace(payload)
                ? new TransportAttempt(null, requestWriteStarted)
                : new TransportAttempt(ReportWireCodec.DeserializeResponse(payload!), requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private sealed class TransportAttempt
    {
        public TransportAttempt(ReportResponse? response, bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public ReportResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
