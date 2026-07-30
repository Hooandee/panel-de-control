using System;
using System.Threading.Tasks;
using Windows.ApplicationModel;

namespace PanelDeControl.GameBar;

internal static class HardwareBrokerLauncher
{
    private static readonly object SyncRoot = new();
    private static Task? launchInProgress;

    public static Task EnsureStartedAsync()
    {
        lock (SyncRoot)
        {
            launchInProgress ??= LaunchAndResetAsync();
            return launchInProgress;
        }
    }

    private static async Task LaunchAndResetAsync()
    {
        try
        {
            await FullTrustProcessLauncher.LaunchFullTrustProcessForCurrentAppAsync(
                "HardwareBroker");
            await Task.Delay(250);
        }
        finally
        {
            lock (SyncRoot)
            {
                launchInProgress = null;
            }
        }
    }
}
