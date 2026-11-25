namespace PanelDeControl.Core.Upscalers;

/// <summary>What OptiScaler's own log shows, the way the Linux backend's <c>logread</c> reads it; only what Windows reports.</summary>
public sealed class OptiScalerLogFacts
{
    public const int MaximumBytes = OptiScalerLog.MaximumBytes;
    public const string LogName = OptiScalerLog.LogName;

    private OptiScalerLogFacts(bool present, DateTime? modified, bool? upscalerCreated)
    {
        Present = present;
        Modified = modified;
        UpscalerCreated = upscalerCreated;
    }

    public bool Present { get; }

    public DateTime? Modified { get; }

    /// <summary>Null when there is no log to say either way.</summary>
    public bool? UpscalerCreated { get; }

    public static OptiScalerLogFacts Read(string target)
    {
        var report = OptiScalerLog.Read(target);
        if (!report.Present)
        {
            return new OptiScalerLogFacts(File.Exists(Path.Combine(target, LogName)), null, null);
        }

        return new OptiScalerLogFacts(true, report.Modified, !string.IsNullOrEmpty(report.Upscaler));
    }
}
