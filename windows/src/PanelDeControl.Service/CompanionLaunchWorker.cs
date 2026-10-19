using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using Microsoft.Extensions.Hosting;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

/// <summary>
/// Starts the packaged companion for the signed-in user through its app execution alias, which
/// keeps the package identity the companion needs for its pipes and Steam themes.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class CompanionLaunchWorker : BackgroundService
{
    private const string Alias = "PanelDeControlCompanion.exe";
    private static readonly TimeSpan Poll = TimeSpan.FromSeconds(5);

    private readonly CompanionLaunchPolicy policy = new();

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(Poll, stoppingToken).ConfigureAwait(false);
                var session = WTSGetActiveConsoleSessionId();
                if (session == uint.MaxValue)
                {
                    continue;
                }

                var steam = InSession("steam", session);
                var companion = InSession("PanelDeControl.Hardware", session);
                if (policy.ShouldLaunch(steam, companion, DateTimeOffset.UtcNow))
                {
                    Launch(session);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                CompanionLog.Write("service.companion_launch", exception);
            }
        }
    }

    private static bool InSession(string name, uint session)
    {
        var processes = Process.GetProcessesByName(name);
        try
        {
            return processes.Any(process => process.SessionId == session);
        }
        finally
        {
            foreach (var process in processes)
            {
                process.Dispose();
            }
        }
    }

    private static void Launch(uint session)
    {
        if (!WTSQueryUserToken(session, out var token))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "No user token for the console session");
        }

        var environment = IntPtr.Zero;
        try
        {
            var profile = new System.Text.StringBuilder(260);
            var size = (uint)profile.Capacity;
            if (!GetUserProfileDirectory(token, profile, ref size))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "User profile is unavailable");
            }

            var alias = Path.Combine(profile.ToString(), "AppData", "Local", "Microsoft", "WindowsApps", Alias);
            if (!CreateEnvironmentBlock(out environment, token, false))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "User environment is unavailable");
            }

            var startup = new StartupInfo { cb = Marshal.SizeOf<StartupInfo>(), lpDesktop = @"winsta0\default" };
            if (!CreateProcessAsUser(token, alias, null, IntPtr.Zero, IntPtr.Zero, false,
                    CreateUnicodeEnvironment | CreateNoWindow, environment, profile.ToString(), ref startup, out var info))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), $"Companion alias did not start ({alias})");
            }

            CloseHandle(info.hThread);
            CloseHandle(info.hProcess);
            CompanionLog.Write("service.companion_launch", $"started in session {session}");
        }
        finally
        {
            if (environment != IntPtr.Zero)
            {
                DestroyEnvironmentBlock(environment);
            }

            CloseHandle(token);
        }
    }

    private const uint CreateUnicodeEnvironment = 0x00000400;
    private const uint CreateNoWindow = 0x08000000;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo
    {
        public int cb;
        public string? lpReserved;
        public string? lpDesktop;
        public string? lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    [DllImport("kernel32.dll")]
    private static extern uint WTSGetActiveConsoleSessionId();

    [DllImport("wtsapi32.dll", SetLastError = true)]
    private static extern bool WTSQueryUserToken(uint sessionId, out IntPtr token);

    [DllImport("userenv.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool GetUserProfileDirectory(IntPtr token, System.Text.StringBuilder path, ref uint size);

    [DllImport("userenv.dll", SetLastError = true)]
    private static extern bool CreateEnvironmentBlock(out IntPtr environment, IntPtr token, bool inherit);

    [DllImport("userenv.dll", SetLastError = true)]
    private static extern bool DestroyEnvironmentBlock(IntPtr environment);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CreateProcessAsUser(IntPtr token, string application, string? commandLine,
        IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint creationFlags,
        IntPtr environment, string currentDirectory, ref StartupInfo startupInfo, out ProcessInformation processInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);
}
