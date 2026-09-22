using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;

namespace PanelDeControl.Service;

public sealed record PipeAccessEntry(
    WellKnownSidType Identity,
    PipeAccessRights Rights,
    AccessControlType Access);

public static class ServicePipeSecurity
{
    public const string PipeName = PanelDeControl.Hardware.ServiceSnapshotClient.PipeName;

    public static IReadOnlyList<PipeAccessEntry> Entries { get; } = new[]
    {
        new PipeAccessEntry(WellKnownSidType.NetworkSid, PipeAccessRights.FullControl, AccessControlType.Deny),
        new PipeAccessEntry(WellKnownSidType.LocalSystemSid, PipeAccessRights.FullControl, AccessControlType.Allow),
        new PipeAccessEntry(WellKnownSidType.AuthenticatedUserSid, PipeAccessRights.ReadWrite, AccessControlType.Allow),
    };

    public static NamedPipeServerStream Create(string pipeName)
    {
        var security = new PipeSecurity();
        foreach (var entry in Entries)
        {
            security.AddAccessRule(new PipeAccessRule(
                new SecurityIdentifier(entry.Identity, null),
                entry.Rights,
                entry.Access));
        }

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
}
