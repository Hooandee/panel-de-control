using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class ServicePipeSecurityTests
{
    [Fact]
    public void NetworkClientsAreDeniedBeforeAnyGrant()
    {
        var first = ServicePipeSecurity.Entries[0];

        Assert.Equal(WellKnownSidType.NetworkSid, first.Identity);
        Assert.Equal(AccessControlType.Deny, first.Access);
        Assert.Equal(PipeAccessRights.FullControl, first.Rights);
    }

    [Fact]
    public void OnlySystemGetsFullControlAndUsersCanOnlyReadWrite()
    {
        var grants = ServicePipeSecurity.Entries
            .Where(entry => entry.Access == AccessControlType.Allow)
            .ToDictionary(entry => entry.Identity, entry => entry.Rights);

        Assert.Equal(2, grants.Count);
        Assert.Equal(PipeAccessRights.FullControl, grants[WellKnownSidType.LocalSystemSid]);
        Assert.Equal(PipeAccessRights.ReadWrite, grants[WellKnownSidType.AuthenticatedUserSid]);
        Assert.DoesNotContain(ServicePipeSecurity.Entries, entry => entry.Identity == WellKnownSidType.WorldSid);
    }

    [Fact]
    public void PipeIsNotInTheAppContainerLocalNamespace()
    {
        Assert.DoesNotContain("LOCAL\\", ServicePipeSecurity.PipeName, StringComparison.Ordinal);
        Assert.Equal("PanelDeControlService", Program.ServiceName);
    }

    [Fact]
    public void TdpWritePipeIsNarrowerThanTheReadPipe()
    {
        var grants = TdpServicePipeSecurity.Entries
            .Where(entry => entry.Access == AccessControlType.Allow)
            .ToDictionary(entry => entry.Identity, entry => entry.Rights);

        Assert.Equal(PipeAccessRights.FullControl, grants[WellKnownSidType.LocalSystemSid]);
        Assert.Equal(PipeAccessRights.ReadWrite, grants[WellKnownSidType.InteractiveSid]);
        Assert.Equal(2, grants.Count);
        var first = TdpServicePipeSecurity.Entries[0];
        Assert.Equal(WellKnownSidType.NetworkSid, first.Identity);
        Assert.Equal(AccessControlType.Deny, first.Access);
        Assert.Equal(PipeAccessRights.FullControl, first.Rights);
        Assert.DoesNotContain(TdpServicePipeSecurity.Entries,
            entry => entry.Identity == WellKnownSidType.WorldSid);
        Assert.DoesNotContain(
            TdpServicePipeSecurity.Entries,
            entry => entry.Identity == WellKnownSidType.AuthenticatedUserSid);
        Assert.NotEqual(ServicePipeSecurity.PipeName, TdpServicePipeSecurity.PipeName);
    }
}
