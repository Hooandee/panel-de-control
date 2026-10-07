using System.Diagnostics;
using System.Management;
using System.Runtime.Versioning;
using Microsoft.Win32;

namespace PanelDeControl.Hardware.Themes;

public interface ISteamInstallation
{
    string? SteamPath { get; }

    bool DebuggingEnabled { get; }

    bool BetaClient { get; }

    bool IsRunning { get; }

    void EnableDebugging();

    Task RestartAsync(bool bigPicture, CancellationToken cancellationToken);
}

/// <summary>
/// The per-user Steam install found through <c>HKCU\Software\Valve\Steam</c>. Steam grants users
/// full control of its folder, so the debugging flag and theme assets need no elevation.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class SteamInstallation : ISteamInstallation
{
    public const string DebuggingFlagFile = ".cef-enable-remote-debugging";

    public string? SteamPath
    {
        get
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            var path = key?.GetValue("SteamPath") as string;
            return path is not null && File.Exists(Path.Combine(path, "steam.exe"))
                ? Path.GetFullPath(path)
                : null;
        }
    }

    public bool DebuggingEnabled => SteamPath is { } path && File.Exists(Path.Combine(path, DebuggingFlagFile));

    public bool BetaClient => SteamPath is { } path && File.Exists(Path.Combine(path, "package", "beta"));

    public bool IsRunning => Process.GetProcessesByName("steam").Length > 0;

    public void EnableDebugging()
    {
        var path = SteamPath ?? throw new InvalidOperationException("Steam is not installed");
        using (File.Create(Path.Combine(path, DebuggingFlagFile)))
        {
        }
    }

    // Steam is driven through its URL protocol and handed to the already running Explorer, so it
    // starts outside this package; a child of a packaged app inherits the package's virtual AppData.
    public async Task RestartAsync(bool bigPicture, CancellationToken cancellationToken)
    {
        _ = SteamPath ?? throw new InvalidOperationException("Steam is not installed");
        bigPicture |= RunningInBigPicture();
        if (IsRunning)
        {
            OpenSteamUrl("steam://exit");
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(45);
            while (IsRunning && DateTime.UtcNow < deadline)
            {
                await Task.Delay(500, cancellationToken).ConfigureAwait(false);
            }

            if (IsRunning)
            {
                throw new TimeoutException("Steam did not close");
            }
        }

        OpenSteamUrl(bigPicture ? "steam://open/bigpicture" : "steam://open/main");
    }

    private static void OpenSteamUrl(string url)
    {
        var explorer = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe");
        using (Process.Start(new ProcessStartInfo(explorer, url) { UseShellExecute = false }))
        {
        }
    }

    private static bool RunningInBigPicture()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT CommandLine FROM Win32_Process WHERE Name = 'steam.exe'");
            return searcher.Get()
                .Cast<ManagementObject>()
                .Any(process => (process["CommandLine"] as string)?.Contains("-gamepadui", StringComparison.OrdinalIgnoreCase) == true);
        }
        catch (ManagementException)
        {
            return false;
        }
    }
}
