using System.Globalization;
using System.Text.Json;
using PanelDeControl.Hardware.Themes;

namespace PanelDeControl.Hardware.Upscalers;

public enum SteamLaunchOptionsOutcome
{
    Written,
    Read,
    SteamUnavailable,
    Failed,
}

/// <param name="Value">The launch options read from Steam, or the value now confirmed after a write.</param>
/// <param name="Reason">Short machine-readable cause when <see cref="Outcome"/> is <see cref="SteamLaunchOptionsOutcome.Failed"/>.</param>
public sealed record SteamLaunchOptionsResult(SteamLaunchOptionsOutcome Outcome, string? Value = null, string? Reason = null)
{
    public bool Succeeded => Outcome is SteamLaunchOptionsOutcome.Written or SteamLaunchOptionsOutcome.Read;
}

public interface ISteamLaunchOptions
{
    Task<SteamLaunchOptionsResult> ReadAsync(long appId, CancellationToken cancellationToken);

    Task<SteamLaunchOptionsResult> WriteAsync(long appId, string value, bool isNonSteamShortcut, CancellationToken cancellationToken);
}

/// <summary>Reads and writes a game's Steam launch options through the Steam client's own UI context. Never throws.</summary>
public sealed class SteamLaunchOptions : ISteamLaunchOptions
{
    private const int ConfirmAttempts = 3;
    private static readonly TimeSpan ConfirmDelay = TimeSpan.FromMilliseconds(120);

    private readonly ISteamDevTools devTools;

    public SteamLaunchOptions(ISteamDevTools devTools)
    {
        this.devTools = devTools;
    }

    public static string ReadScript(long appId)
    {
        var id = appId.ToString(CultureInfo.InvariantCulture);
        return "new Promise(resolve => {"
            + "let done = false, registration;"
            + "const finish = value => { if (done) return; done = true;"
            + " try { registration && registration.unregister && registration.unregister(); } catch (e) {}"
            + " resolve(value); };"
            + "try { registration = window.SteamClient.Apps.RegisterForAppDetails(" + id + ","
            + " details => { if (details && typeof details.strLaunchOptions === 'string') finish({ ok: true, launch: details.strLaunchOptions }); });"
            + " if (done && registration && registration.unregister) registration.unregister(); } catch (e) {}"
            + "setTimeout(() => { try { const details = window.appDetailsStore && window.appDetailsStore.GetAppDetails(" + id + ");"
            + " finish(details && typeof details.strLaunchOptions === 'string' ? { ok: true, launch: details.strLaunchOptions } : { ok: false, reason: 'unreadable' }); }"
            + " catch (e) { finish({ ok: false, reason: 'unreadable' }); } }, 1200); })";
    }

    public static string WriteScript(long appId, string value, bool isNonSteamShortcut)
    {
        var id = appId.ToString(CultureInfo.InvariantCulture);
        var setter = isNonSteamShortcut ? "SetShortcutLaunchOptions" : "SetAppLaunchOptions";
        return "(() => { try { const apps = window.SteamClient && window.SteamClient.Apps;"
            + " if (!apps || typeof apps." + setter + " !== 'function') return { ok: false, reason: 'no_setter' };"
            + " apps." + setter + "(" + id + ", " + JsonSerializer.Serialize(value) + "); return { ok: true }; }"
            + " catch (e) { return { ok: false, reason: 'setter_failed' }; } })()";
    }

    public async Task<SteamLaunchOptionsResult> ReadAsync(long appId, CancellationToken cancellationToken)
    {
        return await RunAsync(session => ReadCoreAsync(session, appId, cancellationToken), cancellationToken).ConfigureAwait(false);
    }

    public async Task<SteamLaunchOptionsResult> WriteAsync(long appId, string value, bool isNonSteamShortcut, CancellationToken cancellationToken)
    {
        return await RunAsync(
            async session =>
            {
                var write = await session.EvaluateAsync(WriteScript(appId, value, isNonSteamShortcut), cancellationToken).ConfigureAwait(false);
                if (!Succeeded(write, out var reason))
                {
                    return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Failed, null, reason);
                }

                for (var attempt = 0; attempt < ConfirmAttempts; attempt++)
                {
                    if (attempt > 0)
                    {
                        await Task.Delay(ConfirmDelay, cancellationToken).ConfigureAwait(false);
                    }

                    var read = await ReadCoreAsync(session, appId, cancellationToken).ConfigureAwait(false);
                    if (read.Outcome == SteamLaunchOptionsOutcome.Read && string.Equals(read.Value, value, StringComparison.Ordinal))
                    {
                        return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Written, value);
                    }
                }

                return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Failed, null, "unconfirmed");
            },
            cancellationToken).ConfigureAwait(false);
    }

    private static async Task<SteamLaunchOptionsResult> ReadCoreAsync(ICdpSession session, long appId, CancellationToken cancellationToken)
    {
        var result = await session.EvaluateAsync(ReadScript(appId), cancellationToken).ConfigureAwait(false);
        if (!Succeeded(result, out var reason))
        {
            return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Failed, null, reason);
        }

        var launch = result.TryGetProperty("launch", out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : string.Empty;
        return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Read, launch);
    }

    private static bool Succeeded(JsonElement result, out string reason)
    {
        if (result.ValueKind == JsonValueKind.Object
            && result.TryGetProperty("ok", out var ok)
            && ok.ValueKind == JsonValueKind.True)
        {
            reason = string.Empty;
            return true;
        }

        reason = result.ValueKind == JsonValueKind.Object && result.TryGetProperty("reason", out var found) && found.ValueKind == JsonValueKind.String
            ? found.GetString() ?? "failed"
            : "failed";
        return false;
    }

    private async Task<SteamLaunchOptionsResult> RunAsync(Func<ICdpSession, Task<SteamLaunchOptionsResult>> action, CancellationToken cancellationToken)
    {
        ICdpSession? session = null;
        try
        {
            var targets = await devTools.ListTargetsAsync(cancellationToken).ConfigureAwait(false);
            var shared = targets?.FirstOrDefault(target => target.Title == SteamThemeEngine.SharedContextTitle);
            if (shared is null)
            {
                return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.SteamUnavailable);
            }

            session = await devTools.ConnectAsync(shared, cancellationToken).ConfigureAwait(false);
            return await action(session).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Failed, null, "cancelled");
        }
        catch (Exception exception) when (exception is CdpException or System.Net.WebSockets.WebSocketException or System.Net.Http.HttpRequestException or JsonException or InvalidOperationException or IOException or KeyNotFoundException)
        {
            return new SteamLaunchOptionsResult(SteamLaunchOptionsOutcome.Failed, null, "cdp_failed");
        }
        finally
        {
            if (session is not null)
            {
                await session.DisposeAsync().ConfigureAwait(false);
            }
        }
    }
}
