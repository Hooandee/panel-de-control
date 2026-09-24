using System.Buffers.Binary;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using PanelDeControl.Core.Telemetry;

namespace PanelDeControl.Service;

public enum AsusSensorRegister : uint
{
    CpuFan = 0x00110013,
    GpuFan = 0x00110014,
    CpuTemperature = 0x00120094,
    GpuTemperature = 0x00120097,
}

public interface IAsusSensorTransport
{
    uint? Read(AsusSensorRegister register);
}

public sealed class AsusAtkSensorTransport : IAsusSensorTransport
{
    public uint? Read(AsusSensorRegister register)
    {
        if (!OperatingSystem.IsWindows()) return null;
        using var handle = CreateFile(@"\\.\ATKACPI", 0xC0000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
        if (handle.IsInvalid) return null;
        var input = BuildReadFrame(register);
        var output = new byte[16];
        return DeviceIoControl(handle, 0x0022240C, input, input.Length, output, output.Length,
            out var returned, IntPtr.Zero) && returned >= sizeof(uint)
            ? BinaryPrimitives.ReadUInt32LittleEndian(output)
            : null;
    }

    public static byte[] BuildReadFrame(AsusSensorRegister register)
    {
        if (!Enum.IsDefined(register)) throw new ArgumentOutOfRangeException(nameof(register));
        var frame = new byte[16];
        BinaryPrimitives.WriteUInt32LittleEndian(frame, 0x53545344);
        BinaryPrimitives.WriteUInt32LittleEndian(frame.AsSpan(4), 8);
        BinaryPrimitives.WriteUInt32LittleEndian(frame.AsSpan(8), (uint)register);
        return frame;
    }

    public static double? Decode(AsusSensorRegister register, uint? raw)
    {
        if (!Enum.IsDefined(register) || raw is not uint value || (value & 0xFFFF0000) != 0x00010000)
            return null;
        var fan = register is AsusSensorRegister.CpuFan or AsusSensorRegister.GpuFan;
        var reading = (double)(value & 0xFFFF) * (fan ? 100 : 1);
        return SensorPlausibility.IsPlausible(fan ? SensorKind.Fan : SensorKind.Temperature, reading)
            ? reading : null;
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode,
        SetLastError = true, ExactSpelling = true)]
    private static extern SafeFileHandle CreateFile(string fileName, uint desiredAccess, uint shareMode,
        IntPtr securityAttributes, uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);

    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(SafeFileHandle device, uint controlCode, byte[] input,
        int inputSize, byte[] output, int outputSize, out int bytesReturned, IntPtr overlapped);
}
