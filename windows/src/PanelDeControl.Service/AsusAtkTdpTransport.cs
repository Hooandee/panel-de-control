using System.Buffers.Binary;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace PanelDeControl.Service;

public enum AsusTdpRegister : uint
{
    Sppt = 0x001200A0,
    Pl1Spl = 0x001200A3,
    Fppt = 0x001200C1,
}

public enum AsusTdpWriteResult
{
    Accepted,
    Rejected,
    Fault,
}

public readonly record struct AsusTdpReadResult(bool HasValue, int Watts)
{
    public static AsusTdpReadResult Unavailable { get; } = new(false, 0);

    public static AsusTdpReadResult Value(int watts) => new(true, watts);
}

public interface IAsusTdpTransport
{
    AsusTdpWriteResult Write(AsusTdpRegister register, int watts);

    AsusTdpReadResult Read(AsusTdpRegister register);
}

public sealed class AsusAtkTdpTransport : IAsusTdpTransport
{
    private const string DevicePath = @"\\.\ATKACPI";
    private const uint ControlCode = 0x0022240C;
    private const uint Dsts = 0x53545344;
    private const uint Devs = 0x53564544;
    private const uint GenericReadWrite = 0xC0000000;
    private const uint FileShareReadWrite = 0x00000003;
    private const uint OpenExisting = 3;
    private const uint PresenceBit = 0x00010000;
    private const uint AllowedDstsBits = PresenceBit | 0x0000FFFF;

    public AsusTdpWriteResult Write(AsusTdpRegister register, int watts)
    {
        if (!OperatingSystem.IsWindows())
        {
            return AsusTdpWriteResult.Fault;
        }

        var response = Invoke(BuildWriteFrame(register, watts));
        if (response is null)
        {
            return AsusTdpWriteResult.Fault;
        }

        return BinaryPrimitives.ReadInt32LittleEndian(response) == 1
            ? AsusTdpWriteResult.Accepted
            : AsusTdpWriteResult.Rejected;
    }

    public AsusTdpReadResult Read(AsusTdpRegister register)
    {
        if (!OperatingSystem.IsWindows())
        {
            return AsusTdpReadResult.Unavailable;
        }

        var response = Invoke(BuildReadFrame(register));
        return response is null
            ? AsusTdpReadResult.Unavailable
            : ParseDstsCandidate(
                BinaryPrimitives.ReadUInt32LittleEndian(response));
    }

    public static byte[] BuildWriteFrame(
        AsusTdpRegister register,
        int watts)
    {
        if (watts < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(watts));
        }

        var frame = new byte[16];
        BinaryPrimitives.WriteUInt32LittleEndian(frame, Devs);
        BinaryPrimitives.WriteUInt32LittleEndian(frame.AsSpan(4), 8);
        BinaryPrimitives.WriteUInt32LittleEndian(
            frame.AsSpan(8),
            (uint)register);
        BinaryPrimitives.WriteUInt32LittleEndian(
            frame.AsSpan(12),
            (uint)watts);
        return frame;
    }

    public static byte[] BuildReadFrame(AsusTdpRegister register)
    {
        var frame = new byte[16];
        BinaryPrimitives.WriteUInt32LittleEndian(frame, Dsts);
        BinaryPrimitives.WriteUInt32LittleEndian(frame.AsSpan(4), 8);
        BinaryPrimitives.WriteUInt32LittleEndian(
            frame.AsSpan(8),
            (uint)register);
        return frame;
    }

    public static AsusTdpReadResult ParseDstsCandidate(uint raw)
    {
        if ((raw & PresenceBit) == 0 || (raw & ~AllowedDstsBits) != 0)
        {
            return AsusTdpReadResult.Unavailable;
        }

        var watts = (int)(raw & 0x0000FFFF);
        return watts is > 0 and <= 255
            ? AsusTdpReadResult.Value(watts)
            : AsusTdpReadResult.Unavailable;
    }

    private static byte[]? Invoke(byte[] input)
    {
        using var handle = CreateFile(
            DevicePath,
            GenericReadWrite,
            FileShareReadWrite,
            IntPtr.Zero,
            OpenExisting,
            0,
            IntPtr.Zero);
        if (handle.IsInvalid)
        {
            return null;
        }

        var output = new byte[16];
        return DeviceIoControl(
            handle,
            ControlCode,
            input,
            input.Length,
            output,
            output.Length,
            out var returned,
            IntPtr.Zero) && returned >= sizeof(int)
            ? output
            : null;
    }

    [DllImport(
        "kernel32.dll",
        EntryPoint = "CreateFileW",
        CharSet = CharSet.Unicode,
        SetLastError = true,
        ExactSpelling = true)]
    private static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);

    [DllImport(
        "kernel32.dll",
        SetLastError = true,
        ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(
        SafeFileHandle device,
        uint controlCode,
        byte[] input,
        int inputSize,
        byte[] output,
        int outputSize,
        out int bytesReturned,
        IntPtr overlapped);
}
