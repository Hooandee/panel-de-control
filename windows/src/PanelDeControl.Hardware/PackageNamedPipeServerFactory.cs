using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace PanelDeControl.Hardware;

[SupportedOSPlatform("windows")]
public static class PackageNamedPipeServerFactory
{
    private const int ErrorInsufficientBuffer = 122;

    public static NamedPipeServerStream Create(string pipeName)
    {
        return Create(pipeName, includeWorldAccess: true);
    }

    public static NamedPipeServerStream CreateControl(string pipeName)
    {
        return Create(pipeName, includeWorldAccess: false);
    }

    private static NamedPipeServerStream Create(
        string pipeName,
        bool includeWorldAccess)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException();
        }

        var security = new PipeSecurity();
        if (includeWorldAccess)
        {
            AddRule(
                security,
                new SecurityIdentifier(WellKnownSidType.WorldSid, null),
                PipeAccessRights.ReadWrite);
        }

        AddRule(security, ReadCurrentPackageSid(), PipeAccessRights.ReadWrite);

        var currentUser = WindowsIdentity.GetCurrent().User
            ?? throw new InvalidOperationException("Current Windows user SID is unavailable.");
        AddRule(security, currentUser, PipeAccessRights.FullControl);

        return NamedPipeServerStreamAcl.Create(
            pipeName,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous,
            0,
            0,
            security,
            HandleInheritability.None,
            (PipeAccessRights)0);
    }

    private static void AddRule(
        PipeSecurity security,
        IdentityReference identity,
        PipeAccessRights rights)
    {
        security.AddAccessRule(new PipeAccessRule(
            identity,
            rights,
            AccessControlType.Allow));
    }

    private static SecurityIdentifier ReadCurrentPackageSid()
    {
        uint length = 0;
        var result = GetCurrentPackageFamilyName(ref length, null);
        if (result != ErrorInsufficientBuffer || length == 0)
        {
            throw new InvalidOperationException(
                $"Current package family name is unavailable ({result}).");
        }

        var familyName = new StringBuilder((int)length);
        result = GetCurrentPackageFamilyName(ref length, familyName);
        if (result != 0)
        {
            throw new InvalidOperationException(
                $"Current package family name could not be read ({result}).");
        }

        result = DeriveAppContainerSidFromAppContainerName(
            familyName.ToString(),
            out var sidPointer);
        if (result != 0 || sidPointer == IntPtr.Zero)
        {
            throw new InvalidOperationException(
                $"Current package SID could not be derived ({result}).");
        }

        try
        {
            return new SecurityIdentifier(sidPointer);
        }
        finally
        {
            FreeSid(sidPointer);
        }
    }

    [DllImport(
        "kernel32.dll",
        EntryPoint = "GetCurrentPackageFamilyName",
        CharSet = CharSet.Unicode,
        ExactSpelling = true)]
    private static extern int GetCurrentPackageFamilyName(
        ref uint packageFamilyNameLength,
        StringBuilder? packageFamilyName);

    [DllImport(
        "userenv.dll",
        EntryPoint = "DeriveAppContainerSidFromAppContainerName",
        CharSet = CharSet.Unicode,
        ExactSpelling = true)]
    private static extern int DeriveAppContainerSidFromAppContainerName(
        string appContainerName,
        out IntPtr appContainerSid);

    [DllImport(
        "advapi32.dll",
        EntryPoint = "FreeSid",
        ExactSpelling = true)]
    private static extern IntPtr FreeSid(IntPtr sid);
}
