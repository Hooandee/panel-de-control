using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading.Tasks;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.GameBar;

public sealed class UpscalersClient
{
    private const string PipeName = @"LOCAL\PanelDeControl.Upscalers";
    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan ResponseTimeout = TimeSpan.FromSeconds(25);

    public Task<UpscalersResponse> OverviewAsync() => SendAsync(UpscalersRequest.Overview());

    public Task<UpscalersResponse> GameAsync(string appId) => SendAsync(UpscalersRequest.Game(appId));

    public Task<UpscalersResponse> CoverAsync(string appId) => SendAsync(UpscalersRequest.Cover(appId));

    public Task<UpscalersResponse> JobAsync() => SendAsync(UpscalersRequest.Job());

    public Task<UpscalersResponse> InstallAsync(string appId, string build, string? quality, string? model, bool experimental) =>
        SendAsync(UpscalersRequest.Install(appId, build, quality, model, experimental));

    public Task<UpscalersResponse> UninstallAsync(string appId, bool experimental) =>
        SendAsync(UpscalersRequest.Uninstall(appId, experimental));

    public Task<UpscalersResponse> ConfigureAsync(string appId, string? quality, string? sharpness, bool frameGen, string? frameGenRoute, string? model, bool experimental) =>
        SendAsync(UpscalersRequest.Configure(appId, quality, sharpness, frameGen, frameGenRoute, model, experimental));

    public Task<UpscalersResponse> IniAsync(string appId) => SendAsync(UpscalersRequest.Ini(appId));

    public Task<UpscalersResponse> SetIniAsync(string appId, string key, string value, bool experimental) =>
        SendAsync(UpscalersRequest.SetIni(appId, key, value, experimental));

    public Task<UpscalersResponse> VerifyAsync(string appId) => SendAsync(UpscalersRequest.Verify(appId));

    public Task<UpscalersResponse> CancelAsync(bool experimental) => SendAsync(UpscalersRequest.Cancel(experimental));

    public Task<UpscalersResponse> SetExeAsync(string appId, string? exe, bool experimental) =>
        SendAsync(UpscalersRequest.SetExe(appId, exe, experimental));

    public Task<UpscalersResponse> ImageAsync(string appId) => SendAsync(UpscalersRequest.Image(appId));

    public Task<UpscalersResponse> SetImageAsync(string appId, bool? sharpnessEnabled, double? sharpnessValue, string? int8, bool experimental) =>
        SendAsync(UpscalersRequest.SetImage(appId, sharpnessEnabled, sharpnessValue, int8, experimental));

    public Task<UpscalersResponse> RestoreImageAsync(string appId, bool experimental) =>
        SendAsync(UpscalersRequest.RestoreImage(appId, experimental));

    private static async Task<UpscalersResponse> SendAsync(UpscalersRequest request)
    {
        string payload;
        try
        {
            payload = UpscalersWireCodec.SerializeRequest(request);
        }
        catch
        {
            return Failure("invalid_upscalers_request");
        }

        var attempt = await TrySendAsync(payload);
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
                return Failure("upscalers_broker_launch_failed");
            }

            attempt = await TrySendAsync(payload);
            if (attempt.Response is not null)
            {
                return attempt.Response;
            }
        }

        return Failure(attempt.RequestWriteStarted ? "upscalers_response_unavailable" : "upscalers_broker_unreachable");
    }

    private static async Task<TransportAttempt> TrySendAsync(string payload)
    {
        var requestWriteStarted = false;
        try
        {
            using var pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync((int)ConnectTimeout.TotalMilliseconds);
            using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, leaveOpen: true);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 1024, leaveOpen: true) { AutoFlush = true };

            requestWriteStarted = true;
            await writer.WriteLineAsync(payload);

            var readTask = reader.ReadLineAsync();
            if (await Task.WhenAny(readTask, Task.Delay(ResponseTimeout)) != readTask)
            {
                return new TransportAttempt(null, requestWriteStarted);
            }

            var line = await readTask;
            return string.IsNullOrWhiteSpace(line) || line.Length > UpscalersWireCodec.MaximumResponseLength
                ? new TransportAttempt(null, requestWriteStarted)
                : new TransportAttempt(UpscalersWireCodec.DeserializeResponse(line), requestWriteStarted);
        }
        catch
        {
            return new TransportAttempt(null, requestWriteStarted);
        }
    }

    private static UpscalersResponse Failure(string errorCode) => UpscalersResponse.Fault(errorCode);

    private sealed class TransportAttempt
    {
        public TransportAttempt(UpscalersResponse? response, bool requestWriteStarted)
        {
            Response = response;
            RequestWriteStarted = requestWriteStarted;
        }

        public UpscalersResponse? Response { get; }

        public bool RequestWriteStarted { get; }
    }
}
