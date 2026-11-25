using System.IO.Pipes;
using System.Text;
using PanelDeControl.Core.Reports;
using PanelDeControl.Hardware.Reports;

namespace PanelDeControl.Hardware;

/// <summary>
/// <c>LOCAL\PanelDeControl.Reports</c>: one request line in, one response line out. Reports are served one at a
/// time; a report is never cut short once its upload started, so the widget cannot see a failure for a report
/// that did arrive.
/// </summary>
public sealed class ReportPipeServer
{
    public const string PackagedPipeName = @"LOCAL\PanelDeControl.Reports";

    private readonly string pipeName;
    private readonly IReportController controller;
    private readonly Func<string, NamedPipeServerStream> pipeFactory;

    public ReportPipeServer(string pipeName, IReportController controller, Func<string, NamedPipeServerStream> pipeFactory)
    {
        this.pipeName = pipeName;
        this.controller = controller;
        this.pipeFactory = pipeFactory;
    }

    public async Task RunUntilCancelledAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await RunOnceAsync(cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    public async Task RunOnceAsync(CancellationToken cancellationToken)
    {
        await using var server = await PipeInstances.CreateAsync(pipeFactory, pipeName, cancellationToken).ConfigureAwait(false);
        using var clientRelease = PipeClientRelease.For(server);
        await server.WaitForConnectionAsync(cancellationToken).ConfigureAwait(false);

        using var reader = new StreamReader(server, new UTF8Encoding(false), false, 1024, leaveOpen: true);
        var writer = new StreamWriter(server, new UTF8Encoding(false), 1024, leaveOpen: true) { AutoFlush = true };
        try
        {
            var payload = await ReadLineAsync(reader, cancellationToken).ConfigureAwait(false);
            if (payload.Disconnected)
            {
                return;
            }

            var response = payload.TooLong
                ? ReportResponse.Rejected("report_request_too_long")
                : await HandleAsync(payload.Value ?? string.Empty, cancellationToken).ConfigureAwait(false);
            try
            {
                await writer.WriteLineAsync(ReportWireCodec.SerializeResponse(response)).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is IOException or ObjectDisposedException)
            {
            }
        }
        finally
        {
            try
            {
                await writer.DisposeAsync().ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is IOException or ObjectDisposedException)
            {
            }
        }
    }

    private async Task<ReportResponse> HandleAsync(string payload, CancellationToken cancellationToken)
    {
        ReportRequest request;
        try
        {
            request = ReportWireCodec.DeserializeRequest(payload);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            return ReportResponse.Rejected(exception is InvalidDataException { Message: var code } && code.StartsWith("report_", StringComparison.Ordinal)
                ? code
                : "invalid_report_request");
        }

        try
        {
            return await controller.SendAsync(request, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            CompanionLog.Write("report.send", exception);
            return ReportResponse.Rejected("report_failed");
        }
    }

    private static async Task<PipeRequest> ReadLineAsync(StreamReader reader, CancellationToken cancellationToken)
    {
        var line = new StringBuilder();
        var buffer = new char[1];
        while (true)
        {
            if (await reader.ReadAsync(buffer.AsMemory(0, 1), cancellationToken).ConfigureAwait(false) == 0)
            {
                return new PipeRequest(null, false, true);
            }

            switch (buffer[0])
            {
                case '\n':
                    return new PipeRequest(line.ToString(), false, false);
                case '\r':
                    continue;
            }

            if (line.Length == ReportWireCodec.MaximumRequestLength)
            {
                return new PipeRequest(null, true, false);
            }

            line.Append(buffer[0]);
        }
    }

    private readonly record struct PipeRequest(string? Value, bool TooLong, bool Disconnected);
}
