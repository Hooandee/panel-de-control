namespace PanelDeControl.Core.Upscalers;

/// <summary>What a Panel install's OptiScaler log says since it went in, as the Linux game page reports it.</summary>
public sealed class UpscalerVerdict
{
    public string Verdict { get; private set; } = OptiScalerLog.NotRun;

    public string? Observed { get; private set; }

    public string? Provider { get; private set; }

    public string? Fallback { get; private set; }

    /// <summary>Null for engines without an OptiScaler log (DLL mode).</summary>
    public static UpscalerVerdict? Read(InstalledUpscaler install, double installedAt)
    {
        installedAt = Math.Max(installedAt, install.VerificationSince ?? 0);
        if (install.Engine == "helixsr" && !string.IsNullOrEmpty(install.Target))
        {
            var facts = HelixLog.ReadInstall(install, installedAt);
            return new UpscalerVerdict { Verdict = HelixLog.Verdict(facts), Observed = facts.Upscaler };
        }
        if (install.Engine != "optiscaler" || string.IsNullOrEmpty(install.Target))
        {
            return null;
        }
        var report = OptiScalerLog.Read(install.Target, Since(installedAt));
        var provider = OptiScalerLog.ProviderObservationOf(report);
        var fallback = OptiScalerLog.FallbackOf(install.Engine, install.Build, report);
        return new UpscalerVerdict
        {
            Verdict = OptiScalerLog.Verdict(report),
            Observed = report.Upscaler,
            Provider = provider?.Name is { Length: > 0 } name
                ? string.Join(" ", new[] { name, provider.Version, provider.Model }.Where(part => !string.IsNullOrEmpty(part)))
                : null,
            Fallback = fallback?.Observed,
        };
    }

    /// <summary>The install time Panel stores (Unix seconds) as the UTC instant a fresh log must come after.</summary>
    public static DateTime? Since(double installedAt) =>
        installedAt > 0 ? DateTimeOffset.FromUnixTimeMilliseconds((long)(installedAt * 1000)).UtcDateTime : null;
}
