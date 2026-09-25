using System.IO.Pipes;

namespace PanelDeControl.Hardware;

public sealed class PackagedWidgetClientValidator : IPipeClientValidator
{
    public const string WidgetRelativePath = "PanelDeControl.GameBar.exe";

    public bool IsTrusted(NamedPipeServerStream pipe)
    {
        var client = PackagedPipeClient.DescribeClient(pipe);
        return client is not null &&
            PackagedPipeClient.IsExpected(
                client.ExecutablePath,
                client.PackageFamilyName,
                PackagedPipeClient.CurrentFamilyName(),
                client.PackagePath,
                WidgetRelativePath);
    }
}
