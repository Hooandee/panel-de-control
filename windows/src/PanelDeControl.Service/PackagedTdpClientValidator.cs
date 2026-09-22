using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace PanelDeControl.Service;

public interface ITdpClientValidator
{
    bool IsTrusted(NamedPipeServerStream pipe);
}

public sealed class PackagedTdpClientValidator : ITdpClientValidator
{
    private const uint ProcessQueryLimitedInformation = 0x1000;
    private const int ErrorInsufficientBuffer = 122;
    private const int MaximumPathLength = 32768;
    private const string PackageNamePrefix = "PanelDeControl.Windows_";
    private const string BrokerExecutableName = "PanelDeControl.Hardware.exe";

    public bool IsTrusted(NamedPipeServerStream pipe)
    {
        if (!OperatingSystem.IsWindows() ||
            !GetNamedPipeClientProcessId(pipe.SafePipeHandle, out var processId))
        {
            return false;
        }

        using var process = OpenProcess(
            ProcessQueryLimitedInformation,
            false,
            processId);
        if (process.IsInvalid)
        {
            return false;
        }

        var path = new StringBuilder(MaximumPathLength);
        var pathLength = path.Capacity;
        if (!QueryFullProcessImageName(process, 0, path, ref pathLength))
        {
            return false;
        }

        uint packageLength = 0;
        var packageResult = GetPackageFullName(process, ref packageLength, null);
        if (packageResult != ErrorInsufficientBuffer || packageLength == 0)
        {
            return false;
        }

        var package = new StringBuilder((int)packageLength);
        if (GetPackageFullName(process, ref packageLength, package) != 0)
        {
            return false;
        }

        return IsTrustedIdentity(path.ToString(), package.ToString());
    }

    public static bool IsTrustedIdentity(
        string? executablePath,
        string? packageFullName)
    {
        var normalizedPath = executablePath?.Replace('\\', '/');
        return string.Equals(
                Path.GetFileName(normalizedPath),
                BrokerExecutableName,
                StringComparison.OrdinalIgnoreCase) &&
            packageFullName?.StartsWith(
                PackageNamePrefix,
                StringComparison.Ordinal) == true;
    }

    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeClientProcessId(
        SafePipeHandle pipe,
        out uint clientProcessId);

    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    private static extern SafeProcessHandle OpenProcess(
        uint desiredAccess,
        [MarshalAs(UnmanagedType.Bool)] bool inheritHandle,
        uint processId);

    [DllImport(
        "kernel32.dll",
        EntryPoint = "QueryFullProcessImageNameW",
        CharSet = CharSet.Unicode,
        SetLastError = true,
        ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(
        SafeProcessHandle process,
        uint flags,
        StringBuilder executableName,
        ref int size);

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        SetLastError = true,
        ExactSpelling = true)]
    private static extern int GetPackageFullName(
        SafeProcessHandle process,
        ref uint packageFullNameLength,
        StringBuilder? packageFullName);
}
