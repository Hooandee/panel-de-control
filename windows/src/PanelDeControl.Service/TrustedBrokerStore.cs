using System.Text.Json;
using PanelDeControl.Hardware;

namespace PanelDeControl.Service;

/// <summary>
/// The companion fingerprint the elevated installer recorded next to the service, in Program Files where
/// only administrators write. Without a record no companion is trusted.
/// </summary>
public sealed class TrustedBrokerStore
{
    public const string FileName = "trusted-broker.json";

    private readonly string recordPath;
    private readonly object gate = new();
    private DateTime recordWrittenUtc;
    private string? trustedFingerprint;
    private string? verifiedShape;
    private string? verifiedDirectory;

    public TrustedBrokerStore(string recordPath)
    {
        this.recordPath = recordPath;
    }

    public static TrustedBrokerStore NextToService() =>
        new(Path.Combine(AppContext.BaseDirectory, FileName));

    /// <summary>Records the fingerprint of the companion folder that was just installed.</summary>
    public static void Record(string recordPath, string brokerDirectory)
    {
        var json = JsonSerializer.Serialize(new { fingerprint = BrokerFingerprint.Compute(brokerDirectory) });
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
                recordWrittenUtc = written;
                verifiedShape = null;
            }

            return !string.IsNullOrEmpty(trustedFingerprint);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            trustedFingerprint = null;
            return false;
        }
    }
}
