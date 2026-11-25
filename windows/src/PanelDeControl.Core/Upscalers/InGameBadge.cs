using System.Globalization;

namespace PanelDeControl.Core.Upscalers;

/// <summary>When the in-game badge shows; Linux keeps this in the front end and defaults to <c>off</c>, Windows defaults to <c>start</c>.</summary>
public static class InGameModes
{
    public const string Off = "off";
    public const string Start = "start";
    public const string Always = "always";
    public const string Default = Start;

    public static readonly TimeSpan StartWindow = TimeSpan.FromSeconds(6);

    public static bool IsValid(string? mode) => mode is Off or Start or Always;

    public static string Normalize(string? mode) => IsValid(mode) ? mode! : Default;
}

public enum BadgeTone
{
    Normal,
    Muted,
    Warn,
}

public sealed class BadgeSpan
{
    public BadgeSpan(string text, BadgeTone tone)
    {
        Text = text;
        Tone = tone;
    }

    public string Text { get; }

    public BadgeTone Tone { get; }
}

/// <summary>One opaque box of the badge: its spans sit side by side.</summary>
public sealed class BadgeLine
{
    public BadgeLine(IReadOnlyList<BadgeSpan> spans)
    {
        Spans = spans;
    }

    public IReadOnlyList<BadgeSpan> Spans { get; }

    public string Text => string.Join(" ", Spans.Select(span => span.Text));
}

/// <summary>What the badge says about one game right now, the way the Linux pill reads its live data.</summary>
public sealed class InGameFacts
{
    public string Label { get; set; } = "";

    public string Engine { get; set; } = "optiscaler";

    /// <summary>The log shows the upscaler running. DLL mode has no log, so it never is.</summary>
    public bool Active { get; set; }

    /// <summary>The family the installed build belongs to: <c>fsr</c> or <c>xess</c>.</summary>
    public string? BuildFamily { get; set; }

    public ProviderObservation? Observation { get; set; }

    public Fsr4Fallback? Fallback { get; set; }

    public int? RenderHeight { get; set; }

    public int? OutputHeight { get; set; }

    public bool FrameGen { get; set; }

    public string? FrameGenRoute { get; set; }

    /// <summary>Null while the log has not said either way.</summary>
    public bool? Generating { get; set; }

    public bool InstalledDll => Engine == "dll";
}

/// <summary>The badge's words in the six languages the product ships.</summary>
public sealed class InGameText
{
    private static readonly Dictionary<string, string[]> Table = new(StringComparer.Ordinal)
    {
        ["es"] = new[] { "{0} no disponible en este juego · usando {1}", "{0} no disponible en este juego", "Generando frames", "Pausado", "Configurado" },
        ["en"] = new[] { "{0} not available in this game · using {1}", "{0} not available in this game", "Generating frames", "Paused", "Configured" },
        ["de"] = new[] { "{0} in diesem Spiel nicht verfügbar · nutzt {1}", "{0} in diesem Spiel nicht verfügbar", "Frames werden generiert", "Pausiert", "Konfiguriert" },
        ["fr"] = new[] { "{0} indisponible dans ce jeu · utilise {1}", "{0} indisponible dans ce jeu", "Génération de frames active", "En pause", "Configuré" },
        ["it"] = new[] { "{0} non disponibile in questo gioco · uso {1}", "{0} non disponibile in questo gioco", "Generazione di frame attiva", "In pausa", "Configurato" },
        ["pt"] = new[] { "{0} indisponível neste jogo · usando {1}", "{0} indisponível neste jogo", "Gerando frames", "Pausado", "Configurado" },
    };

    private readonly string[] words;

    public InGameText(string? language)
    {
        var key = (language ?? string.Empty).Split('-', '_')[0].ToLowerInvariant();
        words = Table.TryGetValue(key, out var found) ? found : Table["en"];
    }

    public static InGameText ForCulture(CultureInfo culture) => new(culture.Name);

    public string Fallback(Fsr4Fallback fallback) => string.Format(
        CultureInfo.InvariantCulture,
        fallback.Observed is null ? words[1] : words[0],
        fallback.Requested,
        fallback.Observed);

    public string Generating => words[2];

    public string Paused => words[3];

    public string Configured => words[4];
}

/// <summary>The lines of the badge (<c>InGameBadge</c> on Linux, minus the engines Windows does not have).</summary>
public static class InGameContent
{
    public static bool HasContent(InGameFacts? facts) => facts is not null && (facts.InstalledDll || facts.Active);

    public static IReadOnlyList<BadgeLine> Lines(InGameFacts facts, InGameText text)
    {
        var lines = new List<BadgeLine>();
        if (!HasContent(facts))
        {
            return lines;
        }

        var first = new List<BadgeSpan>
        {
            facts.Fallback is { } fallback
                ? new BadgeSpan(text.Fallback(fallback), BadgeTone.Warn)
                : new BadgeSpan(ObservedProvider(facts) ?? facts.Label, BadgeTone.Normal),
        };
        if (facts.RenderHeight is { } render && facts.OutputHeight is { } output)
        {
            first.Add(new BadgeSpan(string.Format(CultureInfo.InvariantCulture, "{0}p → {1}p", render, output), BadgeTone.Muted));
        }

        lines.Add(new BadgeLine(first));
        if (facts.FrameGen)
        {
            var state = facts.Generating switch
            {
                true => text.Generating,
                false => text.Paused,
                _ => text.Configured,
            };
            lines.Add(new BadgeLine(new[]
            {
                new BadgeSpan(FrameGenName(facts.FrameGenRoute), BadgeTone.Normal),
                new BadgeSpan(state, BadgeTone.Muted),
            }));
        }

        return lines;
    }

    public static string FrameGenName(string? route) => route == "anr" ? "Apex ANR" : "OptiScaler";

    /// <summary>The scaler the log shows when it is another one than the build's, or a version the build's name does not carry.</summary>
    public static string? ObservedProvider(InGameFacts facts)
    {
        if (facts.Observation is not { } observation)
        {
            return null;
        }

        var other = !string.IsNullOrEmpty(observation.Family) && !string.IsNullOrEmpty(facts.BuildFamily)
            && !facts.InstalledDll && observation.Family != facts.BuildFamily;
        if (other)
        {
            return string.Join(" ", new[] { observation.Name, observation.Version }.Where(part => !string.IsNullOrEmpty(part)));
        }

        return observation.Source == "optiscaler_log" && observation.Confidence != "log_provider"
            && !string.IsNullOrEmpty(observation.Name) && !string.IsNullOrEmpty(observation.Version)
            ? observation.Name + " " + observation.Version
            : null;
    }
}

/// <summary>Whether the badge shows: decided from the mode, the game in front and a clock handed in, never a timer.</summary>
public sealed class InGameBadgePolicy
{
    private const int RememberedRuns = 32;

    private readonly HashSet<string> started = new(StringComparer.Ordinal);
    private DateTimeOffset windowEnds;
    private string? windowRun;

    /// <param name="run">The game in front (its app id and the process it runs as), or null when none is.</param>
    public bool Visible(DateTimeOffset now, string mode, string? run, bool hasContent)
    {
        if (run is null || !hasContent)
        {
            return false;
        }

        if (started.Add(run))
        {
            if (started.Count > RememberedRuns)
            {
                started.Clear();
                started.Add(run);
            }

            windowRun = run;
            windowEnds = now + InGameModes.StartWindow;
        }

        return mode switch
        {
            InGameModes.Always => true,
            InGameModes.Start => windowRun == run && now < windowEnds,
            _ => false,
        };
    }
}
