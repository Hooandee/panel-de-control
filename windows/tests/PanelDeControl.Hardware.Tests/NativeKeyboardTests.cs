using System.Text.Json;
using PanelDeControl.Hardware.NativeKeyboard;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class NativeKeyboardTests
{
    [Fact]
    public async Task ActivationNeedsLiveReadbackAndDisableNeedsRestorationReceipt()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        Assert.Equal("applying", (await controller.SetEnabledAsync(true, CancellationToken.None)).Status);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 7));
        Assert.Equal("applied", controller.Status.Status);
        Assert.Equal(7, controller.Status.StyledKeys);
        var stopping = controller.SetEnabledAsync(false, CancellationToken.None);
        await host.StopRequested.Task;
        Assert.Equal("restoring", controller.Status.Status);
        Assert.False(controller.Status.Requested);
        host.Emit(Receipt("disabled", restored: 7));
        host.Finish();
        Assert.Equal("disabled", (await stopping).Status);
        Assert.Equal(7, controller.Status.RestoredKeys);
        Assert.False(controller.Status.Connected);
    }

    [Fact]
    public async Task ProcessExitWithoutRestoreReceiptDoesNotClaimOriginalAppearance()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 3));
        var stopping = controller.SetEnabledAsync(false, CancellationToken.None);
        await host.StopRequested.Task;
        host.Finish();
        Assert.Equal("restore_unconfirmed", (await stopping).Status);
    }

    [Fact]
    public async Task DisableTimeoutCancelsOnlyHostAndLateReceiptCannotOverwriteState()
    {
        var host = new Host(ignoreCancellation: true);
        await using var controller = new NativeKeyboardController(host, stopTimeout: TimeSpan.FromMilliseconds(30));
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        var result = await controller.SetEnabledAsync(false, CancellationToken.None);
        Assert.Equal("restore_unconfirmed", result.Status);
        host.Emit(Receipt("applied", styled: 4));
        Assert.Equal("restore_unconfirmed", controller.Status.Status);
        host.Finish();
    }

    [Theory]
    [InlineData("{\"status\":\"applied\"}")]
    [InlineData("not json")]
    public async Task MalformedReceiptStopsSessionWithoutLeakingOutput(string output)
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(output);
        await Eventually(() => controller.Status.ErrorCode == "invalid_runtime_response");
        Assert.NotEqual("applied", controller.Status.Status);
    }

    [Fact]
    public async Task AppliedWithoutKeysAndWrongBuildAreRejected()
    {
        foreach (var receipt in new[] { Receipt("applied"), Receipt("applied", styled: 1, build: 26200) })
        {
            var host = new Host();
            await using var controller = new NativeKeyboardController(host);
            await controller.SetEnabledAsync(true, CancellationToken.None);
            await host.Started.Task;
            host.Emit(receipt);
            await Eventually(() => controller.Status.ErrorCode == "invalid_runtime_response");
        }
    }

    [Fact]
    public async Task WaitingIsNotAppliedAndReceiptsCanFollowAReplacementKeyboard()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("waiting_for_keyboard", pid: 0));
        Assert.True(controller.Status.Requested);
        Assert.False(controller.Status.Connected);
        host.Emit(Receipt("applied", styled: 12, pid: 99));
        Assert.Equal(99, controller.Status.ProcessId);
        Assert.Equal("applied", controller.Status.Status);
        host.Finish();
    }

    [Fact]
    public async Task ReplacementKeyboardCanWaitForXamlAndRecoverWithoutReactivation()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 40, pid: 16740));
        Assert.Equal("applied", controller.Status.Status);
        Assert.Equal(40, controller.Status.StyledKeys);
        Assert.Equal(16740, controller.Status.ProcessId);

        host.Emit(Receipt("waiting_for_keyboard", pid: 17200,
            errorCode: "xaml_framework_not_observed", connected: false));
        Assert.True(controller.Status.Requested);
        Assert.Equal("waiting_for_keyboard", controller.Status.Status);
        Assert.Equal("xaml_framework_not_observed", controller.Status.ErrorCode);
        Assert.Equal(17200, controller.Status.ProcessId);
        Assert.False(controller.Status.Connected);
        Assert.Equal(0, controller.Status.StyledKeys);
        Assert.Equal(0, controller.Status.KeyCount);
        Assert.False(host.StopRequested.Task.IsCompleted);

        host.Emit(Receipt("applied", styled: 40, pid: 17200));
        Assert.True(controller.Status.Requested);
        Assert.Equal("applied", controller.Status.Status);
        Assert.Equal("styles_active", controller.Status.ErrorCode);
        Assert.Equal(17200, controller.Status.ProcessId);
        Assert.True(controller.Status.Connected);
        Assert.Equal(40, controller.Status.StyledKeys);
        Assert.Equal(40, controller.Status.KeyCount);
        Assert.Equal(1, host.Starts);
        host.Finish();
    }

    [Fact]
    public async Task MissingRuntimeAndSilenceNeverRestartAutomatically()
    {
        var absent = new Host(available: false);
        await using var missing = new NativeKeyboardController(absent);
        Assert.Equal("runtime_missing", (await missing.SetEnabledAsync(true, CancellationToken.None)).Status);
        Assert.False(absent.Started.Task.IsCompleted);
        var host = new Host();
        await using var controller = new NativeKeyboardController(host, receiptTimeout: TimeSpan.FromMilliseconds(30));
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await Eventually(() => controller.Status.ErrorCode == "runtime_timeout");
        Assert.True(controller.Status.Requested);
        Assert.Equal(1, host.Starts);
    }

    [Fact]
    public async Task DiagnosticsDiscardUnknownProperties()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 1).Insert(1, "\"Text\":\"private input\","));
        Assert.DoesNotContain("private input", controller.Status.Diagnostics);
        Assert.Contains("styledKeys", controller.Status.Diagnostics);
        host.Finish();
    }

    [Fact]
    public async Task DiagnosticsKeepOnlyValidatedFontMetadata()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        var samples = "[{\"family\":\"Original Family-1._`, Fallback\",\"role\":1,\"kind\":1,\"size\":16,\"opacity\":0.5,\"visible\":1,\"Text\":\"private input\"}]";
        host.Emit(Receipt("applied", styled: 1).Insert(1, "\"fontSamples\":" + samples + ","));
        Assert.Equal("applied", controller.Status.Status);
        using var diagnostics = JsonDocument.Parse(controller.Status.Diagnostics!);
        var font = diagnostics.RootElement.GetProperty("fontSamples")[0];
        Assert.Equal("Original Family-1._`, Fallback", font.GetProperty("family").GetString());
        Assert.Equal(16f, font.GetProperty("size").GetSingle());
        Assert.Equal(0.5f, font.GetProperty("opacity").GetSingle());
        Assert.Equal(1u, font.GetProperty("role").GetUInt32());
        Assert.Equal(1u, font.GetProperty("kind").GetUInt32());
        Assert.Equal(1u, font.GetProperty("visible").GetUInt32());
        Assert.DoesNotContain("private input", controller.Status.Diagnostics);
        host.Finish();
    }

    [Theory]
    [InlineData("")]
    [InlineData("C:\\Users\\private")]
    [InlineData("ms-appx:///Assets/font.ttf")]
    [InlineData("font\"secret")]
    [InlineData("font's")]
    [InlineData("font/secret")]
    [InlineData("Fuente ñ")]
    public async Task UnsafeFontFamilyCannotEnterDiagnostics(string family)
    {
        var sample = JsonSerializer.Serialize(new { family, role = 0, kind = 0, size = 16, opacity = 1, visible = 1 });
        await AssertInvalidFonts("[" + sample + "]");
    }

    [Fact]
    public async Task FontMetadataRejectsInvalidFieldsAndOversizedCatalog()
    {
        const string sample = "{\"family\":\"Original Family\",\"role\":0,\"kind\":0,\"size\":16,\"opacity\":1,\"visible\":1}";
        foreach (var invalid in new[]
        {
            sample.Replace("\"role\":0", "\"role\":2"),
            sample.Replace("\"kind\":0", "\"kind\":2"),
            sample.Replace("\"visible\":1", "\"visible\":2"),
            sample.Replace("\"size\":16", "\"size\":-1"),
            sample.Replace("\"size\":16", "\"size\":1025"),
            sample.Replace("\"size\":16", "\"size\":1e100"),
            sample.Replace("\"size\":16", "\"size\":\"NaN\""),
            sample.Replace("\"opacity\":1", "\"opacity\":-0.1"),
            sample.Replace("\"opacity\":1", "\"opacity\":1.1"),
            sample.Replace("Original Family", new string('a', 128)),
            sample.Replace("\"kind\":0,", ""),
        }) await AssertInvalidFonts("[" + invalid + "]");
        await AssertInvalidFonts("[" + string.Join(",", Enumerable.Repeat(sample, 17)) + "]");
        await AssertInvalidFonts("{}");
    }

    private static async Task AssertInvalidFonts(string samples)
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 1).Insert(1, "\"fontSamples\":" + samples + ","));
        Assert.Equal("invalid_runtime_response", controller.Status.ErrorCode);
        Assert.DoesNotContain("Original Family", controller.Status.Diagnostics);
        host.Finish();
    }

    [Fact]
    public async Task ExplicitRetryAfterLostHostRequiresFreshAppliedReceipt()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("applied", styled: 3));
        host.Finish();
        await Eventually(() => controller.Status.Status == "connection_failed");
        Assert.Equal("restore_unconfirmed", (await controller.SetEnabledAsync(false, CancellationToken.None)).Status);
        host.Reset();
        Assert.Equal("applying", (await controller.SetEnabledAsync(true, CancellationToken.None)).Status);
        await Eventually(() => host.Starts == 2);
        Assert.False(controller.Status.Connected);
        host.Emit(Receipt("applied", styled: 4, pid: 99));
        Assert.Equal("applied", controller.Status.Status);
        Assert.Equal(99, controller.Status.ProcessId);
        host.Finish();
    }

    [Fact]
    public async Task RetryStopsLiveFailedHostBeforeStartingAnother()
    {
        var host = new Host();
        await using var controller = new NativeKeyboardController(host);
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        host.Emit(Receipt("connection_failed"));
        var retry = controller.SetEnabledAsync(true, CancellationToken.None);
        await host.StopRequested.Task;
        Assert.Equal(1, host.Starts);
        host.Emit(Receipt("disabled"));
        host.FinishAndReset();
        Assert.Equal("applying", (await retry).Status);
        await Eventually(() => host.Starts == 2);
        host.Emit(Receipt("applied", styled: 2));
        Assert.Equal("applied", controller.Status.Status);
        host.Finish();
    }

    [Fact]
    public async Task RetryCannotOverlapHostThatIgnoresCancellation()
    {
        var host = new Host(ignoreCancellation: true);
        await using var controller = new NativeKeyboardController(host, stopTimeout: TimeSpan.FromMilliseconds(20));
        await controller.SetEnabledAsync(true, CancellationToken.None);
        await host.Started.Task;
        await controller.SetEnabledAsync(false, CancellationToken.None);
        Assert.Equal("restore_unconfirmed", (await controller.SetEnabledAsync(true, CancellationToken.None)).Status);
        Assert.Equal(1, host.Starts);
        host.Finish();
    }

    private static string Receipt(string status, int styled = 0, int restored = 0, int pid = 41, int build = 26300,
        string? errorCode = null, bool? connected = null) => JsonSerializer.Serialize(new
    {
        status, errorCode = errorCode ?? (status == "applied" ? "styles_active" : status == "disabled" ? "styles_restored" : "keyboard_not_running"), windowsBuild = build, architecture = "x64", processId = pid,
        connected = connected ?? pid != 0, observedElements = 0, nodes = Array.Empty<object>(), hresult = 0,
        styledKeys = styled, restoredKeys = restored, keyCount = styled, pendingKeys = 0, stateCatalog = Array.Empty<string>(),
    });

    private static async Task Eventually(Func<bool> condition)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        while (!condition()) await Task.Delay(10, deadline.Token);
    }

    private sealed class Host(bool available = true, bool ignoreCancellation = false) : INativeKeyboardHost
    {
        private Action<string>? receive;
        private TaskCompletionSource finished = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource StopRequested { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Starts { get; private set; }
        public bool Available => available;
        public async Task RunAsync(Action<string> onReceipt, CancellationToken token)
        {
            Starts++;
            receive = onReceipt;
            Started.TrySetResult();
            if (ignoreCancellation) await finished.Task;
            else await finished.Task.WaitAsync(token);
        }
        public Task RequestStopAsync(CancellationToken token) { StopRequested.TrySetResult(); return Task.CompletedTask; }
        public void Emit(string json) => receive!(json);
        public void Finish() => finished.TrySetResult();
        public void Reset() => finished = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public void FinishAndReset() { var previous = finished; Reset(); previous.TrySetResult(); }
    }
}
