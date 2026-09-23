using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace PanelDeControl.Hardware;

public interface IPipeClientValidator
{
    bool IsTrusted(NamedPipeServerStream pipe);
}

public sealed record PackagedProcess(
    string ExecutablePath,
    string PackageFamilyName,
    string PackagePath);

public static class PackagedPipeClient
{
    private const uint ProcessQueryLimitedInformation = 0x1000;
    private const int ErrorInsufficientBuffer = 122;
    private const int MaximumPathLength = 32768;

    public static bool IsExpected(
        string? executablePath,
        string? packageFamilyName,
        string? expectedPackageFamilyName,
        string? packagePath,
        string relativeExecutablePath)
    {
        var normalizedRoot = NormalizePath(packagePath);
        var expectedPath = normalizedRoot is null
            ? null
            : normalizedRoot + "\\" + relativeExecutablePath;
        return expectedPath is not null &&
            !string.IsNullOrEmpty(expectedPackageFamilyName) &&
            string.Equals(
                NormalizePath(executablePath),
                expectedPath,
                StringComparison.OrdinalIgnoreCase) &&
            string.Equals(
                packageFamilyName,
                expectedPackageFamilyName,
                StringComparison.OrdinalIgnoreCase);
    }

    public static PackagedProcess? DescribeClient(NamedPipeServerStream pipe)
    {
        if (!OperatingSystem.IsWindows() ||
            !GetNamedPipeClientProcessId(pipe.SafePipeHandle, out var processId))
        {
            return null;
        }

        using var process = OpenProcess(
            ProcessQueryLimitedInformation,
            false,
            processId);
        if (process.IsInvalid)
        {
            return null;
        }

        var path = new StringBuilder(MaximumPathLength);
        var pathLength = path.Capacity;
        if (!QueryFullProcessImageName(process, 0, path, ref pathLength))
        {
            return null;
        }

        var packageFullName = ReadString((ref uint length, StringBuilder? value) =>
            GetPackageFullName(process, ref length, value));
        if (packageFullName is null)
        {
            return null;
        }

        var familyName = ReadString((ref uint length, StringBuilder? value) =>
            PackageFamilyNameFromFullName(packageFullName, ref length, value));
        var packagePath = ReadString((ref uint length, StringBuilder? value) =>
            GetStagedPackagePathByFullName(packageFullName, ref length, value));
        return familyName is null || packagePath is null
            ? null
            : new PackagedProcess(path.ToString(), familyName, packagePath);
    }

    public static string? FamilyNameFromId(string name, string publisher)
    {
        var id = new PackageId
        {
            Name = name,
            Publisher = publisher,
        };
        return ReadString((ref uint length, StringBuilder? value) =>
            PackageFamilyNameFromId(ref id, ref length, value));
    }

    public static string? CurrentFamilyName()
    {
        return OperatingSystem.IsWindows()
            ? ReadString((ref uint length, StringBuilder? value) =>
                GetCurrentPackageFamilyName(ref length, value))
            : null;
    }

    private delegate int StringReader(ref uint length, StringBuilder? value);

    private static string? ReadString(StringReader read)
    {
        uint length = 0;
        if (read(ref length, null) != ErrorInsufficientBuffer || length == 0)
        {
            return null;
        }

        var value = new StringBuilder(checked((int)length));
        return read(ref length, value) == 0 ? value.ToString() : null;
    }

    private static string? NormalizePath(string? value)
    {
        return string.IsNullOrWhiteSpace(value)
            ? null
            : value.Replace('/', '\\').TrimEnd('\\');
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

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int GetPackageFullName(
        SafeProcessHandle process,
        ref uint packageFullNameLength,
        StringBuilder? packageFullName);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int GetCurrentPackageFamilyName(
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int PackageFamilyNameFromFullName(
        string packageFullName,
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int PackageFamilyNameFromId(
        ref PackageId packageId,
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int GetStagedPackagePathByFullName(
        string packageFullName,
        ref uint pathLength,
        StringBuilder? path);
}
