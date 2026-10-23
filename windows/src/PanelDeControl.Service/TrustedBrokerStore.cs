using System.Text.Json;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

/// <summary>
/// The companion the elevated installer recorded next to the service, in Program Files where only
/// administrators write: its exact folder and a fingerprint of its files. Without a record no companion
/// is trusted. A normal install lives under WindowsApps, which only the system writes, so its files
/// cannot change behind the cached check; a folder anywhere else is accepted only when an administrator
/// recorded it as a development layout.
/// </summary>
public sealed class TrustedBrokerStore
{
    public const string FileName = "trusted-broker.json";

    private readonly string recordPath;
    private readonly object gate = new();
    private DateTime recordWrittenUtc;
    private string? trustedFingerprint;
    private string? trustedPath;
    private bool trustedDevelopment;
    private string? verifiedShape;
    private string? verifiedDirectory;

    public TrustedBrokerStore(string recordPath)
    {
        this.recordPath = recordPath;
    }

    public static TrustedBrokerStore NextToService() =>
        new(Path.Combine(AppContext.BaseDirectory, FileName));

    /// <summary>Records the fingerprint of the companion folder that was just installed.</summary>
    public static void Record(string recordPath, string brokerDirectory, bool development)
    {
        var path = Normalize(brokerDirectory);
        if (!development && !IsProtectedPackageFolder(path))
        {
            throw new InvalidOperationException("The companion is not in the protected package folder: " + path);
        }

        var json = JsonSerializer.Serialize(new { fingerprint = BrokerFingerprint.Compute(path), path, development });
        File.WriteAllText(recordPath, json);
    }

    public bool Matches(string brokerDirectory)
    {
        lock (gate)
        {
            if (!LoadRecord() || !Directory.Exists(brokerDirectory))
            {
                return false;
            }

            brokerDirectory = Normalize(brokerDirectory);
            if (!string.Equals(brokerDirectory, trustedPath, StringComparison.OrdinalIgnoreCase) ||
                (!trustedDevelopment && !IsProtectedPackageFolder(brokerDirectory)))
            {
                return false;
            }

            var shape = BrokerFingerprint.Shape(brokerDirectory);
            if (shape == verifiedShape && string.Equals(brokerDirectory, verifiedDirectory, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            if (BrokerFingerprint.Compute(brokerDirectory) != trustedFingerprint)
            {
                return false;
            }

            verifiedShape = shape;
            verifiedDirectory = brokerDirectory;
            return true;
        }
    }

    private static string Normalize(string path) =>
        string.IsNullOrEmpty(path) ? string.Empty : Path.TrimEndingDirectorySeparator(Path.GetFullPath(path));

    // Under %ProgramFiles%\WindowsApps with no junction or link on the way, so the folder really is the
    // system-owned package store.
    private static bool IsProtectedPackageFolder(string path)
    {
        var store = Normalize(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "WindowsApps"));
        if (!path.StartsWith(store + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        for (var folder = new DirectoryInfo(path); folder is not null; folder = folder.Parent)
        {
            if (folder.Exists && folder.Attributes.HasFlag(FileAttributes.ReparsePoint))
            {
                return false;
            }

            if (string.Equals(Normalize(folder.FullName), store, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private bool LoadRecord()
    {
        try
        {
            var written = File.GetLastWriteTimeUtc(recordPath);
            if (!File.Exists(recordPath))
            {
                trustedFingerprint = null;
                return false;
            }

            if (written != recordWrittenUtc || trustedFingerprint is null)
            {
                using var document = JsonDocument.Parse(File.ReadAllText(recordPath));
                trustedFingerprint = document.RootElement.GetProperty("fingerprint").GetString();
                trustedPath = Normalize(document.RootElement.GetProperty("path").GetString() ?? string.Empty);
                trustedDevelopment = document.RootElement.TryGetProperty("development", out var development) && development.GetBoolean();
                recordWrittenUtc = written;
                verifiedShape = null;
            }

            return !string.IsNullOrEmpty(trustedFingerprint) && !string.IsNullOrEmpty(trustedPath);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            trustedFingerprint = null;
            return false;
        }
    }
}
