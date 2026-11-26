using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace PanelDeControl.Core.Upscalers;

public sealed class LogResolution
{
    public LogResolution(int renderWidth, int renderHeight, int outputWidth, int outputHeight)
    {
        RenderWidth = renderWidth;
        RenderHeight = renderHeight;
        OutputWidth = outputWidth;
        OutputHeight = outputHeight;
    }

    public int RenderWidth { get; }

    public int RenderHeight { get; }

    public int OutputWidth { get; }

    public int OutputHeight { get; }
}

/// <summary>What OptiScaler wrote to its log, with the same keys as the Linux backend's <c>logread.read</c>.</summary>
public sealed class OptiScalerLogReport
{
    public bool Present { get; internal set; }

    public DateTime? Modified { get; internal set; }

    /// <summary>When this launch's log started, from the first line's time of day; null when the log was cut or has no clock.</summary>
    public DateTime? Started { get; internal set; }

    /// <summary>The log predates the install, so it says nothing about it.</summary>
    public bool Stale { get; internal set; }

    public string? Version { get; internal set; }

    public string? Proxy { get; internal set; }

    public string? Gpu { get; internal set; }

    public string? Upscaler { get; internal set; }

    /// <summary>FSR2, FSR3 or XeSS: the entry point the game itself used; null when the log does not name one.</summary>
    public string? Input { get; internal set; }

    public string? FrameGeneration { get; internal set; }

    /// <summary>"true" or "false": the last frame generation toggle in the log.</summary>
    public string? FrameGenerationState { get; internal set; }

    /// <summary>"false" when the game's XeFG stays its own and OptiScaler cannot see it.</summary>
    public string? FrameGenerationBlind { get; internal set; }

    public string? Fsr4Model { get; internal set; }

    public string? Fsr4Provider { get; internal set; }

    public LogResolution? InitialResolution { get; internal set; }

    public bool TextureFailure { get; internal set; }

    public string ResolutionSource { get; internal set; } = "unavailable";

    public int Errors { get; internal set; }

    public IReadOnlyList<KeyValuePair<string, int>> ErrorSources { get; internal set; } = Array.Empty<KeyValuePair<string, int>>();
}

public sealed class ProviderObservation
{
    public ProviderObservation(string? family, string? name, string? version, string? model, string source, string confidence)
    {
        Family = family;
        Name = name;
        Version = version;
        Model = model;
        Source = source;
        Confidence = confidence;
    }

    public string? Family { get; }

    public string? Name { get; }

    public string? Version { get; }

    public string? Model { get; }

    public string Source { get; }

    public string Confidence { get; }
}

/// <summary>FSR 4 was installed but the log shows an older FSR (or textures OptiScaler cannot hand to it).</summary>
public sealed class Fsr4Fallback
{
    public Fsr4Fallback(string? observed, string reason)
    {
        Observed = observed;
        Reason = reason;
    }

    public string Requested => "FSR 4";

    public string? Observed { get; }

    /// <summary>"vulkan_textures" or "backend_changed".</summary>
    public string Reason { get; }
}

/// <summary>Port of the Linux backend's <c>upscalers/logread.py</c>: shared/fixtures/upscalers/log_verdicts.json holds its answers.</summary>
public static class OptiScalerLog
{
    public const string LogName = "OptiScaler.log";
    public const int MaximumBytes = 4 * 1024 * 1024;
    public const int HeadBytes = 1024 * 1024;
    public const int AnrFreshSeconds = 25;
    public const string NotRun = "not_run";
    public const string Loaded = "loaded";
    public const string Active = "active";

    private const int ErrorSourceLimit = 6;
    private const int AnrTailBytes = 64 * 1024;
    private const RegexOptions Options = RegexOptions.CultureInvariant;

    private static readonly (string Key, Regex Pattern)[] Facts =
    {
        ("version", new Regex(@"OptiScaler\s+v?(\d+\.\d+[\w.\-]*)", Options)),
        ("proxy", new Regex(@"OptiScaler working as ([A-Za-z0-9_]+\.(?:dll|asi))", Options | RegexOptions.IgnoreCase)),
        ("gpu", new Regex(@"Adapter Desc:\s*(.+)", Options)),
        ("upscaler", new Regex(@"Creating new (.+?) upscaler", Options)),
        ("upscaler", new Regex(@"Creating (.+?) upscaler feature", Options)),
        ("d3d11_upscaler", new Regex(@"NVSDK_NGX_D3D11_CreateFeature Creating new (.+?)(?: w/Dx1[12])? feature", Options)),
        ("xess_input", new Regex(@"(?:^|\]\s+)hk_xess(?:D3D11|D3D12|VK)Execute\s*$", Options)),
        ("fsr_input", new Regex(@"\bffxFsr([23])ContextCreate_(?:Dx11|Dx12|Vk) context created:", Options)),
        ("ffx_input", new Regex(@"(ffxCreateContext_Dx12) context created", Options)),
        ("fg_state", new Regex(@"D3D12_Configure Enabled: (true|false), result|SetEnabled: (true|false), result", Options)),
        ("fg_input", new Regex(@"FrameGen\.FGInput: (\w+)", Options)),
        ("fg_blind", new Regex(@"XeFG passthrough: (false)\s*$", Options)),
        ("fg_context", new Regex(@"(FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0|XeFG context created)", Options)),
        ("upscaler", new Regex(@"init successful for (.+?), upscaler changed", Options)),
        ("fg", new Regex(@"(D3D12_Configure Enabled: true, result: (?:0\b|FFX_API_RETURN_OK)|SetEnabled: true, result: \w*SUCCESS|Nukem.{0,40}(?:initialized|loaded))", Options | RegexOptions.IgnoreCase)),
        ("fsr4_model", new Regex(@"Upscaler support - fsr4: ([a-z0-9 ]+?)(?: \(forced\))?,", Options)),
        ("fsr4_provider", new Regex(@"QueryProvider \S+ provider for 10000: (4\.\d+\.\d+) \*", Options)),
        ("initial_resolution", new Regex(@"Render Resolution:\s*([0-9]{2,5})x([0-9]{2,5}),\s*Display Resolution\s*([0-9]{2,5})x([0-9]{2,5})", Options)),
    };

    private static readonly Regex TextureFailurePattern = new(@"CreateSharedTexture Failed to get memory Win32 handle|Can't process Vulkan textures", Options);
    private static readonly Regex Clock = new(@"^\[([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]+\]", Options);
    private static readonly Regex ErrorLine = new(@"\[(?:E|C)\]\s\s*(?:(?:`anonymous-namespace'::)?([A-Za-z_][\w:]{0,60}))?", Options);
    private static readonly Regex OldFsr = new(@"^(?:FSR (?:(2)\.(\d+)|(3)\.(\d+))(?:\.\d+)?)\z", Options);
    private static readonly Regex AnrPacing = new(@"^\[([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]+\] \[info\] pacing: [0-9]+ real frames .*?evaluates ours ([0-9]+)", Options | RegexOptions.Multiline);
    private static readonly Regex AnrLine = new(@"^\[([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]+\]", Options | RegexOptions.Multiline);
    private static readonly (string Family, Regex Pattern)[] ProviderFamilies =
    {
        ("fsr", ProviderFamily("fsr")),
        ("dlss", ProviderFamily("dlss")),
        ("xess", ProviderFamily("xess")),
    };

    /// <summary>Facts from the newest log; <see cref="OptiScalerLogReport.Stale"/> when it predates <paramref name="since"/> (the install).</summary>
    public static OptiScalerLogReport Read(string target, DateTime? since = null)
    {
        var path = Path.Combine(target, LogName);
        string text;
        DateTime modifiedUtc;
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists)
            {
                return new OptiScalerLogReport();
            }

            modifiedUtc = info.LastWriteTimeUtc;
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            text = DecodeHeadAndTail(stream);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return new OptiScalerLogReport();
        }

        var report = new OptiScalerLogReport { Present = true, Modified = modifiedUtc };
        report.Started = StartOfLog(text, modifiedUtc);

        if (since is { } install && modifiedUtc < install.ToUniversalTime())
        {
            report.Stale = true;
            return report;
        }

        Parse(text, report);
        return report;
    }

    /// <summary>Reads the facts out of log text; <see cref="Read"/> adds the file's times.</summary>
    public static OptiScalerLogReport Parse(string text)
    {
        var report = new OptiScalerLogReport { Present = true };
        Parse(text, report);
        return report;
    }

    public static string Verdict(OptiScalerLogReport report)
    {
        if (!report.Present || report.Stale)
        {
            return NotRun;
        }

        return string.IsNullOrEmpty(report.Upscaler) ? Loaded : Active;
    }

    public static ProviderObservation ProviderObservationOf(OptiScalerLogReport report)
    {
        string? family = null;
        var available = report.Present && !report.Stale;
        if (available && report.Upscaler is { } upscaler)
        {
            var token = upscaler.ToLowerInvariant().Trim();
            foreach (var (candidate, pattern) in ProviderFamilies)
            {
                if (pattern.IsMatch(token))
                {
                    family = candidate;
                    break;
                }
            }
        }

        var older = OldFsr.IsMatch((report.Upscaler ?? string.Empty).Trim());
        var version = family == "fsr" && !older && !report.TextureFailure && !string.IsNullOrEmpty(report.Fsr4Provider) ? report.Fsr4Provider : null;
        var model = version is null ? null : Fsr4Model(report.Fsr4Model);
        var name = family switch { "fsr" => "FSR", "dlss" => "DLSS", "xess" => "XeSS", _ => null };
        return new ProviderObservation(family, name, version, model, available ? "optiscaler_log" : "unavailable",
            version is not null ? "log_provider" : family is not null ? "family_only" : "unknown");
    }

    /// <summary>FSR 4 was installed (<paramref name="build"/> starts with "fsr-4") but the log shows an older FSR; null when nothing says so.</summary>
    public static Fsr4Fallback? FallbackOf(string engine, string build, OptiScalerLogReport report)
    {
        if (engine != "optiscaler" || !build.StartsWith("fsr-4", StringComparison.Ordinal))
        {
            return null;
        }

        if (!report.Present || report.Stale)
        {
            return null;
        }

        var token = (report.Upscaler ?? string.Empty).Trim();
        if (token.StartsWith("FSR 4", StringComparison.Ordinal))
        {
            return null;
        }

        var old = OldFsr.Match(token);
        if (!old.Success && !report.TextureFailure)
        {
            return null;
        }

        string? observed = null;
        if (old.Success)
        {
            var major = old.Groups[1].Success ? old.Groups[1].Value : old.Groups[3].Value;
            var minor = old.Groups[2].Success ? old.Groups[2].Value : old.Groups[4].Value;
            observed = "FSR " + major + "." + minor;
        }

        return new Fsr4Fallback(observed, report.TextureFailure ? "vulkan_textures" : "backend_changed");
    }

    /// <summary>Whether ANR FG generated in the last summaries of its newest <c>nr_fg-*.log</c>; null before it wrote one.</summary>
    public static bool? AnrGenerating(string folder, DateTime nowUtc)
    {
        string tail;
        DateTime modifiedUtc;
        try
        {
            FileInfo? newest = null;
            foreach (var file in new DirectoryInfo(folder).GetFiles("nr_fg-*.log"))
            {
                if (newest is null || file.LastWriteTimeUtc > newest.LastWriteTimeUtc)
                {
                    newest = file;
                }
            }

            if (newest is null)
            {
                return null;
            }

            modifiedUtc = newest.LastWriteTimeUtc;
            using var stream = new FileStream(newest.FullName, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            tail = DecodeTail(stream, AnrTailBytes);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }

        return AnrGenerating(tail, (nowUtc.ToUniversalTime() - modifiedUtc).TotalSeconds);
    }

    /// <summary>The decision itself, given the tail of the log and how long ago the file was last written.</summary>
    public static bool? AnrGenerating(string tail, double secondsSinceModified)
    {
        var summaries = AnrPacing.Matches(tail);
        if (summaries.Count == 0)
        {
            return null;
        }

        var summary = summaries[summaries.Count - 1];
        var lines = AnrLine.Matches(tail);
        var last = lines[lines.Count - 1];
        var sinceSummary = (ClockSeconds(last) - ClockSeconds(summary)) % 86400;
        if (sinceSummary < 0)
        {
            sinceSummary += 86400;
        }

        var generating = summary.Groups[4].Value.Trim('0').Length > 0;
        return generating && secondsSinceModified <= AnrFreshSeconds && sinceSummary <= AnrFreshSeconds;
    }

    private static void Parse(string text, OptiScalerLogReport report)
    {
        var errors = 0;
        var sources = new List<KeyValuePair<string, int>>();
        string? fgContext = null;
        string? fgInput = null;
        foreach (var line in SplitLines(text))
        {
            foreach (var (key, pattern) in Facts)
            {
                var match = pattern.Match(line);
                if (!match.Success)
                {
                    continue;
                }

                switch (key)
                {
                    case "ffx_input":
                        report.Input = "FSR3";
                        break;
                    case "xess_input":
                        report.Input = "XeSS";
                        break;
                    case "fsr_input":
                        report.Input = "FSR" + match.Groups[1].Value;
                        break;
                    case "d3d11_upscaler":
                    case "upscaler":
                        report.Upscaler = Clip(match.Groups[1].Value);
                        break;
                    case "initial_resolution":
                        report.InitialResolution = new LogResolution(
                            int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture), int.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture),
                            int.Parse(match.Groups[3].Value, CultureInfo.InvariantCulture), int.Parse(match.Groups[4].Value, CultureInfo.InvariantCulture));
                        break;
                    default:
                        var value = Clip(FirstGroup(match));
                        switch (key)
                        {
                            case "version": report.Version = value; break;
                            case "proxy": report.Proxy = value; break;
                            case "gpu": report.Gpu = value; break;
                            case "fg_state": report.FrameGenerationState = value; break;
                            case "fg_input": fgInput = value; break;
                            case "fg_blind": report.FrameGenerationBlind = value; break;
                            case "fg_context": fgContext = value; break;
                            case "fg": report.FrameGeneration = value; break;
                            case "fsr4_model": report.Fsr4Model = value; break;
                            case "fsr4_provider": report.Fsr4Provider = value; break;
                        }

                        break;
                }
            }

            var error = ErrorLine.Match(line);
            if (error.Success)
            {
                errors++;
                if (error.Groups[1].Success)
                {
                    var name = error.Groups[1].Value;
                    var index = sources.FindIndex(pair => pair.Key == name);
                    if (index < 0)
                    {
                        sources.Add(new KeyValuePair<string, int>(name, 1));
                    }
                    else
                    {
                        sources[index] = new KeyValuePair<string, int>(name, sources[index].Value + 1);
                    }
                }
            }

            if (TextureFailurePattern.IsMatch(line))
            {
                report.TextureFailure = true;
            }
        }

        if (!string.IsNullOrEmpty(fgContext) && string.Equals(fgInput ?? string.Empty, "upscaler", StringComparison.OrdinalIgnoreCase) && report.FrameGeneration is null)
        {
            report.FrameGeneration = fgContext;
        }

        report.ResolutionSource = report.InitialResolution is null ? "unavailable" : "initialization_only";
        report.Errors = errors;
        report.ErrorSources = sources.OrderByDescending(pair => pair.Value).Take(ErrorSourceLimit).ToList();
    }

    private static string? Fsr4Model(string? model) => model switch
    {
        "int8 lite" => "Lite",
        "int8" => "INT8",
        "fp8" => "FP8",
        _ => null,
    };

    private static Regex ProviderFamily(string candidate) =>
        new("^" + candidate + @"(?:[234]1?| [234](?:\.[0-9x]+)*(?:/4)?(?: lite)?)?\z", Options);

    private static string FirstGroup(Match match)
    {
        for (var index = 1; index < match.Groups.Count; index++)
        {
            if (match.Groups[index].Success)
            {
                return match.Groups[index].Value;
            }
        }

        return string.Empty;
    }

    private static string Clip(string value)
    {
        var trimmed = value.Trim();
        return trimmed.Length > 120 ? trimmed.Substring(0, 120) : trimmed;
    }

    private static int ClockSeconds(Match match) =>
        (int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture) * 3600)
        + (int.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture) * 60)
        + int.Parse(match.Groups[3].Value, CultureInfo.InvariantCulture);

    private static string DecodeHeadAndTail(FileStream stream)
    {
        if (stream.Length <= MaximumBytes + HeadBytes)
        {
            return DecodeTail(stream, MaximumBytes + HeadBytes);
        }

        var head = new byte[HeadBytes];
        var read = ReadFully(stream, head);
        var end = read == 0 ? 0 : Array.LastIndexOf(head, (byte)'\n', read - 1) + 1;
        var utf8 = new UTF8Encoding(false, false);
        return utf8.GetString(head, 0, end) + DecodeTail(stream, MaximumBytes);
    }

    private static int ReadFully(FileStream stream, byte[] buffer)
    {
        var read = 0;
        while (read < buffer.Length)
        {
            var count = stream.Read(buffer, read, buffer.Length - read);
            if (count == 0)
            {
                break;
            }

            read += count;
        }

        return read;
    }

    private static string DecodeTail(FileStream stream, int maximum)
    {
        var length = (int)Math.Min(stream.Length, maximum);
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

        return new UTF8Encoding(false, false).GetString(buffer, 0, read);
    }

    private static DateTime? StartOfLog(string text, DateTime modifiedUtc)
    {
        var first = Clock.Match(text);
        if (!first.Success)
        {
            return null;
        }

        int hour = int.Parse(first.Groups[1].Value, CultureInfo.InvariantCulture);
        int minute = int.Parse(first.Groups[2].Value, CultureInfo.InvariantCulture);
        int second = int.Parse(first.Groups[3].Value, CultureInfo.InvariantCulture);
        if (hour > 23 || minute > 59 || second > 59)
        {
            return null;
        }

        var day = modifiedUtc.ToLocalTime();
        var started = new DateTime(day.Year, day.Month, day.Day, hour, minute, second, DateTimeKind.Local);
        if (started > day)
        {
            started = started.AddDays(-1);
        }

        return started.ToUniversalTime();
    }

    /// <summary>Lines the way Python's <c>str.splitlines</c> cuts them.</summary>
    private static IEnumerable<string> SplitLines(string text)
    {
        var start = 0;
        for (var index = 0; index < text.Length; index++)
        {
            var character = text[index];
            if (character is not ('\n' or '\r' or '\v' or '\f' or '\u001c' or '\u001d' or '\u001e' or '\u0085' or '\u2028' or '\u2029'))
            {
                continue;
            }

            yield return text.Substring(start, index - start);
            if (character == '\r' && index + 1 < text.Length && text[index + 1] == '\n')
            {
                index++;
            }

            start = index + 1;
        }

        if (start < text.Length)
        {
            yield return text.Substring(start);
        }
    }
}
