using System.Text.Json;
using PanelDeControl.Hardware.Themes;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class SteamLaunchOptionsTests
{
    private static readonly DevToolsTarget Shared = new("shared", SteamThemeEngine.SharedContextTitle, "https://steamloopback.host/", "page", "ws://127.0.0.1:8080/devtools/page/shared");

    private readonly FakeDevTools devTools = new();

    [Fact]
    public async Task ReportsSteamUnavailableWithoutDebuggingEndpointOrSharedContext()
    {
        var options = new SteamLaunchOptions(devTools);

        devTools.Targets = null;
        Assert.Equal(SteamLaunchOptionsOutcome.SteamUnavailable, (await options.ReadAsync(1, default)).Outcome);

        devTools.Targets = new[] { new DevToolsTarget("menu", "MainMenu_uid2", "about:blank", "page", "ws://127.0.0.1:8080/x") };
        Assert.Equal(SteamLaunchOptionsOutcome.SteamUnavailable, (await options.WriteAsync(1, "-dx11", false, default)).Outcome);
    }

    [Fact]
    public async Task ReadsTheCurrentLaunchOptions()
    {
        devTools.Stored = "%command% -novid";

        var result = await new SteamLaunchOptions(devTools).ReadAsync(1245620, default);

        Assert.Equal(SteamLaunchOptionsOutcome.Read, result.Outcome);
        Assert.Equal("%command% -novid", result.Value);
        Assert.Contains("RegisterForAppDetails(1245620,", devTools.Expressions[0], StringComparison.Ordinal);
    }

    [Fact]
    public async Task WritesAndConfirmsByReadingBack()
    {
        var result = await new SteamLaunchOptions(devTools).WriteAsync(1245620, "-dx11 \"a b\"", false, default);

        Assert.Equal(SteamLaunchOptionsOutcome.Written, result.Outcome);
        Assert.Equal("-dx11 \"a b\"", devTools.Stored);
        Assert.Contains("SetAppLaunchOptions(1245620, \"-dx11 \\u0022a b\\u0022\")", devTools.Expressions[0], StringComparison.Ordinal);
    }

    [Fact]
    public async Task UsesTheShortcutSetterForNonSteamGames()
    {
        await new SteamLaunchOptions(devTools).WriteAsync(2147483650, "-dx11", true, default);

        Assert.Contains("SetShortcutLaunchOptions(2147483650,", devTools.Expressions[0], StringComparison.Ordinal);
    }

    [Fact]
    public async Task FailsWhenSteamDoesNotKeepTheValue()
    {
        devTools.IgnoreWrites = true;

        var result = await new SteamLaunchOptions(devTools).WriteAsync(1, "-dx11", false, default);

        Assert.Equal(SteamLaunchOptionsOutcome.Failed, result.Outcome);
        Assert.Equal("unconfirmed", result.Reason);
    }

    [Fact]
    public async Task FailsWhenTheSetterIsMissing()
    {
        devTools.SetterError = "no_setter";

        var result = await new SteamLaunchOptions(devTools).WriteAsync(1, "-dx11", false, default);

        Assert.Equal(SteamLaunchOptionsOutcome.Failed, result.Outcome);
        Assert.Equal("no_setter", result.Reason);
    }

    [Fact]
    public async Task NeverThrowsWhenTheSessionBreaks()
    {
        devTools.ThrowOnEvaluate = true;
        var options = new SteamLaunchOptions(devTools);

        Assert.Equal("cdp_failed", (await options.ReadAsync(1, default)).Reason);
        Assert.Equal("cdp_failed", (await options.WriteAsync(1, "-dx11", false, default)).Reason);
        Assert.Equal(SteamLaunchOptionsOutcome.Failed, (await options.ReadAsync(1, new CancellationToken(true))).Outcome);
    }

    private sealed class FakeDevTools : ISteamDevTools
    {
        public IReadOnlyList<DevToolsTarget>? Targets { get; set; } = new[] { Shared };

        public string Stored { get; set; } = string.Empty;

        public bool IgnoreWrites { get; set; }

        public bool ThrowOnEvaluate { get; set; }

        public string? SetterError { get; set; }

        public List<string> Expressions { get; } = new();

        public Task<IReadOnlyList<DevToolsTarget>?> ListTargetsAsync(CancellationToken cancellationToken) => Task.FromResult(Targets);

        public Task<ICdpSession> ConnectAsync(DevToolsTarget target, CancellationToken cancellationToken) =>
            Task.FromResult<ICdpSession>(new Session(this));

        private sealed class Session : ICdpSession
        {
            private readonly FakeDevTools owner;

            public Session(FakeDevTools owner)
            {
                this.owner = owner;
            }

            public bool IsOpen => true;

            public Task<JsonElement> EvaluateAsync(string expression, CancellationToken cancellationToken)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (owner.ThrowOnEvaluate)
                {
                    throw new CdpException("closed");
                }

                owner.Expressions.Add(expression);
                if (expression.Contains("RegisterForAppDetails", StringComparison.Ordinal))
                {
                    return Task.FromResult(Json(new { ok = true, launch = owner.Stored }));
                }

                if (owner.SetterError is not null)
                {
                    return Task.FromResult(Json(new { ok = false, reason = owner.SetterError }));
                }

                if (!owner.IgnoreWrites)
                {
                    var start = expression.IndexOf(", \"", StringComparison.Ordinal) + 2;
                    var end = expression.LastIndexOf("\")", StringComparison.Ordinal) + 1;
                    owner.Stored = JsonSerializer.Deserialize<string>(expression.Substring(start, end - start))!;
                }

                return Task.FromResult(Json(new { ok = true }));
            }

            public ValueTask DisposeAsync() => ValueTask.CompletedTask;

            private static JsonElement Json(object value) => JsonSerializer.SerializeToElement(value);
        }
    }
}
