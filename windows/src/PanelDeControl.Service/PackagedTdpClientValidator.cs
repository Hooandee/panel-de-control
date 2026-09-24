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
    private const string PackageName = "PanelDeControl.Windows";
    private const string PackagePublisher = "CN=Hooandee";
    private const string BrokerRelativePath =
        @"HardwareBroker\PanelDeControl.Hardware.exe";

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

        var packageFullName = package.ToString();
        return TryGetPackageFamilyName(packageFullName, out var familyName) &&
            TryGetExpectedPackageFamilyName(out var expectedFamilyName) &&
            TryGetPackagePath(packageFullName, out var packagePath) &&
            IsTrustedIdentity(
                path.ToString(),
                familyName,
                expectedFamilyName,
                packagePath);
    }

    public static bool IsTrustedIdentity(
        string? executablePath,
        string? packageFamilyName,
        string? expectedPackageFamilyName,
        string? packagePath)
    {
        var normalizedRoot = NormalizePath(packagePath);
        var expectedPath = normalizedRoot is null
            ? null
            : normalizedRoot + "\\" + BrokerRelativePath;
        return string.Equals(
                NormalizePath(executablePath),
                expectedPath,
                StringComparison.OrdinalIgnoreCase) &&
            string.Equals(
                packageFamilyName,
                expectedPackageFamilyName,
                StringComparison.OrdinalIgnoreCase);
    }

    private static string? NormalizePath(string? value)
    {
        return string.IsNullOrWhiteSpace(value)
            ? null
            : value.Replace('/', '\\').TrimEnd('\\');
    }

    private static bool TryGetPackageFamilyName(
        string packageFullName,
        out string familyName)
    {
        familyName = string.Empty;
        uint length = 0;
        if (PackageFamilyNameFromFullName(
                packageFullName,
                ref length,
                null) != ErrorInsufficientBuffer ||
            length == 0)
        {
            return false;
        }

        var value = new StringBuilder(checked((int)length));
        if (PackageFamilyNameFromFullName(
                packageFullName,
                ref length,
                value) != 0)
        {
            return false;
        }

        familyName = value.ToString();
        return true;
    }

    private static bool TryGetExpectedPackageFamilyName(out string familyName)
    {
        familyName = string.Empty;
        var id = new PackageId
        {
            Name = PackageName,
            Publisher = PackagePublisher,
        };
        uint length = 0;
        if (PackageFamilyNameFromId(
                ref id,
                ref length,
                null) != ErrorInsufficientBuffer ||
            length == 0)
        {
            return false;
        }

        var value = new StringBuilder(checked((int)length));
        if (PackageFamilyNameFromId(ref id, ref length, value) != 0)
        {
            return false;
        }

        familyName = value.ToString();
        return true;
    }

    private static bool TryGetPackagePath(
        string packageFullName,
        out string packagePath)
    {
        packagePath = string.Empty;
        uint length = 0;
        if (GetPackagePathByFullName(
                packageFullName,
                ref length,
                null) != ErrorInsufficientBuffer ||
            length == 0)
        {
            return false;
        }

        var value = new StringBuilder(checked((int)length));
        if (GetPackagePathByFullName(
                packageFullName,
                ref length,
                value) != 0)
        {
            return false;
        }

        packagePath = value.ToString();
        return true;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct PackageId
    {
        public uint Reserved;
        public uint ProcessorArchitecture;
        public ulong Version;
        [MarshalAs(UnmanagedType.LPWStr)] public string? Name;
        [MarshalAs(UnmanagedType.LPWStr)] public string? Publisher;
        public IntPtr ResourceId;
        public IntPtr PublisherId;
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

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        ExactSpelling = true)]
    private static extern int PackageFamilyNameFromFullName(
        string packageFullName,
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        ExactSpelling = true)]
    private static extern int PackageFamilyNameFromId(
        ref PackageId packageId,
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport(
        "kernel32.dll",
        CharSet = CharSet.Unicode,
        ExactSpelling = true)]
    private static extern int GetPackagePathByFullName(
        string packageFullName,
        ref uint pathLength,
        StringBuilder? path);
}
