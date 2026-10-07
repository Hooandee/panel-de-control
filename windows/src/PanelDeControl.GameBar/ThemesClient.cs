using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Themes;

namespace PanelDeControl.GameBar;

public sealed class ThemesClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Themes";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan QuickResponseTimeout = TimeSpan.FromSeconds(12);
    private static readonly TimeSpan LongResponseTimeout = TimeSpan.FromSeconds(110);

    public Task<ThemesResponse> GetAsync() => SendAsync(ThemesRequest.Get());

    public Task<ThemesResponse> InstallAsync(string catalogId, string version) => SendAsync(ThemesRequest.Install(catalogId, version));

    public Task<ThemesResponse> SetEnabledAsync(string name, bool enabled) => SendAsync(ThemesRequest.SetEnabled(name, enabled));

    public Task<ThemesResponse> SetOptionAsync(string name, string option, string value) => SendAsync(ThemesRequest.SetOption(name, option, value));

    public Task<ThemesResponse> RestartSteamAsync() => SendAsync(ThemesRequest.RestartSteam());

    private static async Task<ThemesResponse> SendAsync(ThemesRequest request)
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
                return Failure("themes_broker_launch_failed");
            }

            attempt = await TrySendAsync(request);
            if (attempt.Response is not null)
            {
                return attempt.Response;
            }
        }

        return Failure(attempt.RequestWriteStarted ? "themes_response_unavailable" : "themes_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(ThemesRequest request)
    {
        var requestWriteStarted = false;
        try
        {
            using var pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync((int)ConnectTimeout.TotalMilliseconds);
            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 1024, leaveOpen: true) { AutoFlush = true };

            requestWriteStarted = true;
            await writer.WriteLineAsync(ThemesWireCodec.SerializeRequest(request));

            var timeout = request.Operation is ThemesOperation.Install or ThemesOperation.RestartSteam
                ? LongResponseTimeout
                : QuickResponseTimeout;
            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(timeout)) != readTask)
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            var payload = await readTask;
            return string.IsNullOrWhiteSpace(payload) || payload.Length > ThemesWireCodec.MaximumResponseLength
                ? new TransportAttempt(null, requestWriteStarted)
                : new TransportAttempt(ThemesWireCodec.DeserializeResponse(payload), requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static ThemesResponse Failure(string errorCode) => new()
    {
        Status = ThemesResponseStatus.Fault,
        ErrorCode = errorCode,
        Connection = ThemesConnection.SteamNotRunning,
    };

    private sealed class TransportAttempt
    {
        public TransportAttempt(ThemesResponse? response, bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public ThemesResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
