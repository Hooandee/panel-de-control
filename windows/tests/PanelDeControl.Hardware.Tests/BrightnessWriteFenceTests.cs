using PanelDeControl.Hardware;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class BrightnessWriteFenceTests
{
    [Fact]
    public async Task TimedOutWriteBlocksNewWritesUntilThePhysicalCallSettles()
    {
        var fence = new BrightnessWriteFence();
        using var release = new ManualResetEventSlim();
        var writeCount = 0;

        await Assert.ThrowsAsync<TimeoutException>(
            () => Task.Run(
                () => fence.Execute(
                    () =>
                    {
                        Interlocked.Increment(ref writeCount);
                        release.Wait();
                        return 0;
                    },
                    TimeSpan.FromMilliseconds(30))));

        Assert.True(fence.HasActiveWrite);
        var observed = fence.ExecuteRead(
            () => 42,
            TimeSpan.FromSeconds(1));
        Assert.Equal(42, observed);
        Assert.True(fence.HasActiveWrite);
        Assert.Throws<BrightnessWriteInProgressException>(
            () => fence.Execute(
                () =>
                {
                    Interlocked.Increment(ref writeCount);
                    return 0;
                },
                TimeSpan.FromSeconds(1)));
        Assert.Equal(1, Volatile.Read(ref writeCount));

        release.Set();
        Assert.True(
            SpinWait.SpinUntil(
                () => !fence.HasActiveWrite,
                TimeSpan.FromSeconds(1)));

        var result = fence.Execute(
            () =>
            {
                Interlocked.Increment(ref writeCount);
                return 0;
            },
            TimeSpan.FromSeconds(1));

        Assert.Equal(0u, result);
        Assert.Equal(2, Volatile.Read(ref writeCount));
    }
}
