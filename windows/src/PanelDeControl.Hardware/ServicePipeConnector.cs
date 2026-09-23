using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace PanelDeControl.Hardware;

public enum ServicePipeState
{
    Connected,
    NotRunning,
    Busy,
    Untrusted,
}

public static class ServicePipeConnector
{
    private const int ErrorFileNotFound = 2;
    private const string LocalSystemSid = "S-1-5-18";
    private const string BuiltinAdministratorsSid = "S-1-5-32-544";

    public static ServicePipeState Connect(string pipeName, TimeSpan timeout, out NamedPipeClientStream? pipe)
    {
        pipe = null;
        if (!OperatingSystem.IsWindows())
        {
            return ServicePipeState.NotRunning;
        }

        if (!WaitNamedPipe($@"\\.\pipe\{pipeName}", 1) && Marshal.GetLastPInvokeError() == ErrorFileNotFound)
        {
            return ServicePipeState.NotRunning;
        }

        var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous,
            TokenImpersonationLevel.Identification);
        try
        {
            client.Connect((int)timeout.TotalMilliseconds);
        }
        catch (TimeoutException)
        {
            client.Dispose();
            return ServicePipeState.Busy;
        }

        // A non-admin process can create this pipe name before the service starts; only trust a
        // server object owned by SYSTEM or Administrators.
        if (!IsTrustedOwner((client.GetAccessControl().GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier)?.Value))
        {
            client.Dispose();
            return ServicePipeState.Untrusted;
        }

        pipe = client;
        return ServicePipeState.Connected;
    }

    public static bool IsTrustedOwner(string? ownerSid)
    {
        return ownerSid is LocalSystemSid or BuiltinAdministratorsSid;
    }

    [DllImport("kernel32.dll", EntryPoint = "WaitNamedPipeW", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern bool WaitNamedPipe(string name, uint timeout);
}
