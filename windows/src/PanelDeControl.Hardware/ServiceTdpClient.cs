using System.Globalization;
using System.Text;
using PanelDeControl.Core.Controls;

namespace PanelDeControl.Hardware;

public interface ITdpControlProxy
{
    TdpControlResponse Send(TdpControlRequest request);
}

public sealed class ServiceTdpClient : ITdpControlProxy
{
    public const string PipeName = "PanelDeControl.Service.Tdp";

    private static readonly TimeSpan ConnectTimeout =
        TimeSpan.FromMilliseconds(500);
    private static readonly TimeSpan ResponseTimeout =
        TimeSpan.FromSeconds(5);

    public TdpControlResponse Send(TdpControlRequest request)
    {
        var writeStarted = false;
        try
        {
            var state = ServicePipeConnector.Connect(
                PipeName,
                ConnectTimeout,
                out var connected);
            if (connected is null)
            {
                return TransportFailure(
                    request,
                    state == ServicePipeState.NotRunning
                        ? "service_not_running"
                        : "service_tdp_unavailable",
                    writeStarted);
            }

            using var pipe = connected;
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
            writeStarted = true;
            writer.WriteLine(BuildCommand(request));
            var line = reader.ReadLineAsync()
                .WaitAsync(ResponseTimeout)
                .GetAwaiter()
                .GetResult();
            return string.IsNullOrWhiteSpace(line)
                ? TransportFailure(
                    request,
                    "service_tdp_response_unavailable",
                    writeStarted)
                : TdpControlWireCodec.DeserializeResponse(line);
        }
        catch
        {
            return TransportFailure(
                request,
                writeStarted
                    ? "service_tdp_response_unavailable"
                    : "service_tdp_unavailable",
                writeStarted);
        }
    }

    internal static string BuildCommand(TdpControlRequest request)
    {
        return request.Operation switch
        {
            TdpControlOperation.Get => "get",
            TdpControlOperation.EnableExperimental => "experimental on",
            TdpControlOperation.DisableExperimental => "experimental off",
            TdpControlOperation.Set => "set " +
                request.RequestedWatts!.Value.ToString(
                    CultureInfo.InvariantCulture),
            _ => throw new InvalidDataException("Unsupported TDP operation."),
        };
    }

    private static TdpControlResponse TransportFailure(
        TdpControlRequest request,
        string errorCode,
        bool writeStarted)
    {
        return request.Operation == TdpControlOperation.Set && writeStarted
            ? TdpControlResponse.Indeterminate(
                false,
                request.RequestedWatts!.Value,
                errorCode)
            : TdpControlResponse.Fault(false, errorCode);
    }
}
