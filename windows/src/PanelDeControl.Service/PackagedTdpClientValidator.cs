using System.IO.Pipes;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

public sealed class PackagedTdpClientValidator : IPipeClientValidator
{
    private readonly TrustedBrokerStore trustedBroker;

    public PackagedTdpClientValidator(TrustedBrokerStore trustedBroker)
    {
        this.trustedBroker = trustedBroker;
    }

    private const string PackageName = "PanelDeControl.Windows";
    private const string PackagePublisher = "CN=Hooandee";
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
                BrokerRelativePath) &&
            client.PackagePath is { } packagePath &&
            trustedBroker.Matches(Path.Combine(packagePath, Path.GetDirectoryName(BrokerRelativePath)!));
    }
}
