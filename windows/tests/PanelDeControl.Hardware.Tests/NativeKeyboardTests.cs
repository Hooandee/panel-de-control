using PanelDeControl.Hardware.NativeKeyboard;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class NativeKeyboardTests
{
    private const string Discovery = "{\"status\":\"discovery_required\",\"errorCode\":\"selectors_unverified\",\"windowsBuild\":26200,\"architecture\":\"x64\",\"processId\":41,\"connected\":true,\"observedElements\":1,\"nodes\":[{\"id\":1,\"parent\":0,\"type\":\"Windows.UI.Xaml.Controls.Grid\"}]}";

    [Fact]
    public async Task DiscoveryNeverBecomesAppliedAndDisableClearsSessionRequest()
    {
        var controller = new NativeKeyboardController(new Host(_ => Task.FromResult(Discovery)));
        Assert.False(controller.Status.Requested);
        var result = await controller.SetEnabledAsync(true, CancellationToken.None);
        Assert.True(result.Requested);
        Assert.Equal("discovery_required", result.Status);
        Assert.True(result.Connected);
        Assert.Equal(1, result.ObservedElements);
        var disabled = await controller.SetEnabledAsync(false, CancellationToken.None);
        Assert.False(disabled.Requested);
        Assert.Equal("disabled", disabled.Status);
        Assert.False(disabled.Connected);
    }

    [Theory]
    [InlineData("{\"status\":\"applied\"}")]
    [InlineData("{\"status\":\"discovery_required\",\"connected\":true}")]
    [InlineData("not json")]
    [InlineData("{\"status\":\"connection_failed\",\"errorCode\":\"a password could be here\",\"windowsBuild\":26200,\"architecture\":\"x64\",\"processId\":41,\"connected\":false,\"observedElements\":0}")]
    public async Task UntrustedOutputCannotClaimSuccessOrLeakContent(string output)
    {
        var result = await new NativeKeyboardController(new Host(_ => Task.FromResult(output)))
            .SetEnabledAsync(true, CancellationToken.None);
        Assert.Equal("connection_failed", result.Status);
        Assert.Equal("invalid_runtime_response", result.ErrorCode);
        Assert.False(result.Connected);
    }

    [Fact]
    public async Task MissingRuntimeDoesNotExecute()
    {
        var result = await new NativeKeyboardController(new Host(_ => throw new Exception("must not run"), false))
            .SetEnabledAsync(true, CancellationToken.None);
        Assert.True(result.Requested);
        Assert.Equal("runtime_missing", result.Status);
    }

    [Fact]
    public async Task HungRuntimeTimesOutWithoutRetryAndCanBeDisabled()
    {
        var started = 0;
        var pending = new TaskCompletionSource<string>();
        var controller = new NativeKeyboardController(new Host(_ => { started++; return pending.Task; }), TimeSpan.FromMilliseconds(30));
        var result = await controller.SetEnabledAsync(true, CancellationToken.None);
        Assert.Equal("runtime_timeout", result.ErrorCode);
        Assert.Contains("runtime_timeout", result.Diagnostics);
        Assert.Equal(1, started);
        Assert.Equal("disabled", (await controller.SetEnabledAsync(false, CancellationToken.None)).Status);
        pending.SetResult(Discovery);
        Assert.False(controller.Status.Requested);
    }

    [Fact]
    public async Task IncompleteNodeReceiptIsRejected()
    {
        var incomplete = Discovery.Replace("\"nodes\"", "\"missingNodes\"");
        var result = await new NativeKeyboardController(new Host(_ => Task.FromResult(incomplete)))
            .SetEnabledAsync(true, CancellationToken.None);
        Assert.Equal("invalid_runtime_response", result.ErrorCode);
        Assert.NotNull(result.Diagnostics);
    }

    [Fact]
    public async Task DiagnosticExportDropsUnrecognizedFields()
    {
        var output = Discovery.Insert(1, "\"Text\":\"private input\",");
        var result = await new NativeKeyboardController(new Host(_ => Task.FromResult(output)))
            .SetEnabledAsync(true, CancellationToken.None);
        Assert.Equal("discovery_required", result.Status);
        Assert.DoesNotContain("private input", result.Diagnostics);
        Assert.Contains("Windows.UI.Xaml.Controls.Grid", result.Diagnostics);
    }

    [Fact]
    public void WireOperationPreservesDisabledRequestAndOptionalStatus()
    {
        var request = PanelDeControl.Core.Themes.ThemesRequest.SetNativeKeyboard(false);
        var encoded = PanelDeControl.Core.Themes.ThemesWireCodec.SerializeRequest(request);
        var decoded = PanelDeControl.Core.Themes.ThemesWireCodec.DeserializeRequest(encoded);
        Assert.Equal(false, decoded.Enabled);
        Assert.Equal(PanelDeControl.Core.Themes.ThemesOperation.SetNativeKeyboard, decoded.Operation);
        var response = new PanelDeControl.Core.Themes.ThemesResponse();
        var result = PanelDeControl.Core.Themes.ThemesWireCodec.DeserializeResponse(
            PanelDeControl.Core.Themes.ThemesWireCodec.SerializeResponse(response));
        Assert.Null(result.NativeKeyboard);
    }

    private sealed class Host(Func<CancellationToken, Task<string>> discover, bool available = true) : INativeKeyboardHost
    {
        public bool Available => available;
        public Task<string> DiscoverAsync(CancellationToken token) => discover(token);
    }
}
