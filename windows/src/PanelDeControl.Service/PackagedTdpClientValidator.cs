using System.IO.Pipes;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public sealed class PackagedTdpClientValidator : IPipeClientValidator
{
    private const string PackageName = "PanelDeControl.Windows";
    // Unsigned MSIX: Windows only installs it unsigned when the publisher carries this OID.
    private const string PackagePublisher = "CN=Hooandee, OID.2.25.311729368913984317654407730594956997722=1";
    public const string BrokerRelativePath =
        @"HardwareBroker\PanelDeControl.Hardware.exe";

    public bool IsTrusted(NamedPipeServerStream pipe)
    {
        var client = PackagedPipeClient.DescribeClient(pipe);
        return client is not null &&
            PackagedPipeClient.IsExpected(
                client.ExecutablePath,
                client.PackageFamilyName,
                PackagedPipeClient.FamilyNameFromId(PackageName, PackagePublisher),
                client.PackagePath,
                BrokerRelativePath);
    }
}
