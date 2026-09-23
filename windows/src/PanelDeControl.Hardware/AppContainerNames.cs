using System.Security.Cryptography;
using System.Text;

namespace PanelDeControl.Hardware;

public static class AppContainerNames
{
    private const string LocalPrefix = @"LOCAL\";

    // Windows derives an AppContainer SID from the SHA-256 of the lower-cased package family name
    // (UTF-16LE): the first 28 bytes become seven little-endian sub-authorities under S-1-15-2.
    // DeriveAppContainerSidFromAppContainerName returns S_OK with a null SID when called from the
    // package's own full-trust process, so the value is computed instead.
    public static string SidFromPackageFamilyName(string packageFamilyName)
    {
        if (string.IsNullOrWhiteSpace(packageFamilyName))
        {
            throw new ArgumentException("Package family name must not be empty.", nameof(packageFamilyName));
        }

        var hash = SHA256.HashData(Encoding.Unicode.GetBytes(packageFamilyName.ToLowerInvariant()));
        var parts = new uint[7];
        for (var index = 0; index < parts.Length; index++)
        {
            parts[index] = BitConverter.ToUInt32(hash, index * 4);
        }

        return "S-1-15-2-" + string.Join("-", parts);
    }

    // A UWP client's "LOCAL\name" resolves inside its AppContainer namespace; a full-trust server
    // must create the pipe under that same path to be reachable.
    public static string ServerPipeName(string pipeName, int sessionId, string appContainerSid)
    {
        return pipeName.StartsWith(LocalPrefix, StringComparison.OrdinalIgnoreCase)
            ? $@"Sessions\{sessionId}\AppContainerNamedObjects\{appContainerSid}\{pipeName.Substring(LocalPrefix.Length)}"
            : pipeName;
    }
}
