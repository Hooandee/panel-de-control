using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

/// <summary>Reads what an installed game's logs say right now; the OptiScaler log is parsed again only after it changed.</summary>
public sealed class InGameFactsReader
{
    private readonly Func<InstalledUpscaler, bool> isInstalled;
    private readonly string anrProvider;
    private (string Key, OptiScalerLogReport Report)? cached;

    public InGameFactsReader(Func<InstalledUpscaler, bool> isInstalled, string anrProvider)
    {
        this.isInstalled = isInstalled;
        this.anrProvider = anrProvider;
    }

    /// <summary>Null when the install is gone: nothing to say.</summary>
    public InGameFacts? Read(StoredUpscaler stored, UpscalerBuild? build, DateTimeOffset now)
    {
        var install = stored.Install;
        if (!isInstalled(install))
        {
            return null;
        }

        var label = UpscalerLabel.Badge(build, install.Options.Model) ?? install.Build;
        var buildFamily = build is null ? null : build.Family == "xess" ? "xess" : "fsr";
        var frameGen = install.Options.FrameGen;
        var route = install.Options.FrameGenRoute;
        if (install.Engine == "dll")
        {
            return new InGameFacts { Label = label, Engine = "dll", BuildFamily = buildFamily, FrameGen = frameGen, FrameGenRoute = route };
        }

        if (install.Engine == "helixsr")
        {
            var facts = HelixLog.ReadInstall(install, stored.InstalledAt);
            return new InGameFacts
            {
                Label = label,
                Engine = "helixsr",
                BuildFamily = buildFamily,
                Active = HelixLog.Verdict(facts) == OptiScalerLog.Active,
                FrameGen = frameGen,
                FrameGenRoute = route,
            };
        }

        if (string.IsNullOrEmpty(install.Target))
        {
            return null;
        }

        var report = Report(install.Target, stored.InstalledAt);
        var active = OptiScalerLog.Verdict(report) == OptiScalerLog.Active;
        bool? generating = null;
        if (report.FrameGenerationBlind is null)
        {
            if (report.FrameGenerationState is not null)
            {
                generating = report.FrameGenerationState == "true" && report.FrameGeneration is not null;
            }
            else if (report.FrameGeneration is not null)
            {
                generating = true;
            }
        }

        if (install.Anr && frameGen && route == "anr")
        {
            generating = AnrGenerating(install.Target, now.UtcDateTime);
        }

        return new InGameFacts
        {
            Label = label,
            Engine = install.Engine,
            Active = active,
            BuildFamily = buildFamily,
            Observation = OptiScalerLog.ProviderObservationOf(report),
            Fallback = OptiScalerLog.FallbackOf(install.Engine, install.Build, report),
            RenderHeight = report.InitialResolution?.RenderHeight,
            OutputHeight = report.InitialResolution?.OutputHeight,
            FrameGen = frameGen,
            FrameGenRoute = route,
            Generating = generating,
        };
    }

    private bool? AnrGenerating(string target, DateTime nowUtc)
    {
        foreach (var folder in new[]
        {
            Path.Combine(target, "custom", anrProvider, "dlssg"),
            Path.Combine(target, "OptiScaler", "custom", anrProvider, "dlssg"),
        })
        {
            if (Directory.Exists(folder))
            {
                return OptiScalerLog.AnrGenerating(folder, nowUtc);
            }
        }

        return null;
    }

    private OptiScalerLogReport Report(string target, double installedAt)
    {
        string key;
        try
        {
            var info = new FileInfo(Path.Combine(target, OptiScalerLog.LogName));
            key = info.Exists ? $"{info.FullName}|{info.Length}|{info.LastWriteTimeUtc.Ticks}|{installedAt}" : string.Empty;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            key = string.Empty;
        }

        if (key.Length > 0 && cached is { } hit && hit.Key == key)
        {
            return hit.Report;
        }

        var report = OptiScalerLog.Read(target, UpscalerVerdict.Since(installedAt));
        cached = key.Length > 0 ? (key, report) : null;
        return report;
    }
}
