using System.Text;
using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What OptiScaler's own log shows, the way the Linux backend's <c>logread</c> reads it; only what Windows reports.</summary>
public sealed class OptiScalerLogFacts
{
    public const int MaximumBytes = 4 * 1024 * 1024;
    public const string LogName = "OptiScaler.log";

    private static readonly Regex[] Patterns =
    {
        new(@"Creating new (.+?) upscaler", RegexOptions.CultureInvariant),
        new(@"Creating (.+?) upscaler feature", RegexOptions.CultureInvariant),
        new(@"init successful for (.+?), upscaler changed", RegexOptions.CultureInvariant),
    };

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
        var path = Path.Combine(target, LogName);
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists)
            {
                return new OptiScalerLogFacts(false, null, null);
            }

            string text;
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                var length = (int)Math.Min(stream.Length, MaximumBytes);
                stream.Seek(-length, SeekOrigin.End);
                var buffer = new byte[length];
                var read = 0;
                while (read < length)
                {
                    var count = stream.Read(buffer, read, length - read);
                    if (count == 0)
                    {
                        break;
                    }

                    read += count;
                }

                text = new UTF8Encoding(false, false).GetString(buffer, 0, read);
            }

            var created = Patterns.Any(pattern => pattern.IsMatch(text));
            return new OptiScalerLogFacts(true, info.LastWriteTimeUtc, created);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return new OptiScalerLogFacts(File.Exists(path), null, null);
        }
    }
}
