using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace PanelDeControl.Hardware;

/// <summary>
/// Windows' MMDeviceEnumerator. COM gives every caller in the process the same object and .NET keeps one wrapper for
/// it, typed after whoever made it first: a <c>[ComImport]</c> class per caller makes every later one fail to cast,
/// and a final release would cut that wrapper from under the other callers. Each caller casts to its own interface.
/// </summary>
[SupportedOSPlatform("windows")]
internal static class CoreAudioDeviceEnumerator
{
    private static readonly Guid ClassId = new("BCDE0395-E52F-467C-8E3D-C4579291692E");

    public static T Create<T>()
        where T : class =>
        (T)Activator.CreateInstance(Type.GetTypeFromCLSID(ClassId, throwOnError: true)!)!;

    public static void Release(object? enumerator)
    {
        if (enumerator is not null && Marshal.IsComObject(enumerator))
        {
            Marshal.ReleaseComObject(enumerator);
        }
    }
}
