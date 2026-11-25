namespace PanelDeControl.Core.Upscalers;

public sealed class ExeCandidate
{
    public ExeCandidate(string exe, IReadOnlyList<string> apis, long size, int score)
    {
        Exe = exe;
        Apis = apis;
        Size = size;
        Score = score;
    }

    /// <summary>Path relative to the game folder, '/'-separated.</summary>
    public string Exe { get; }

    public IReadOnlyList<string> Apis { get; }

    public long Size { get; }

    public int Score { get; }
}

public sealed class GameAnalysis
{
    public GameAnalysis(
        IReadOnlyList<ExeCandidate> candidates,
        string? exe,
        IReadOnlyList<string> apis,
        bool manual,
        string? target,
        IReadOnlyList<KeyValuePair<string, IReadOnlyList<string>>> inputs,
        IReadOnlyList<string> dllTargets,
        int? streamline,
        bool antiCheat,
        bool foreign,
        ForeignIdentity? foreignIdentity)
    {
        Candidates = candidates;
        Exe = exe;
        Apis = apis;
        Manual = manual;
        Target = target;
        Inputs = inputs;
        DllTargets = dllTargets;
        Streamline = streamline;
        AntiCheat = antiCheat;
        Foreign = foreign;
        ForeignIdentity = foreignIdentity;
    }

    public IReadOnlyList<ExeCandidate> Candidates { get; }

    /// <summary>The executable that creates the device, relative to the game folder.</summary>
    public string? Exe { get; }

    public IReadOnlyList<string> Apis { get; }

    /// <summary>The user picked <see cref="Exe"/>.</summary>
    public bool Manual { get; }

    /// <summary>The folder that holds <see cref="Exe"/>, where an upscaler would go.</summary>
    public string? Target { get; }

    /// <summary>Game files that reveal each input kind, relative to the game folder.</summary>
    public IReadOnlyList<KeyValuePair<string, IReadOnlyList<string>>> Inputs { get; }

    /// <summary>Combined FidelityFX libraries the game owns, checked against the chosen build.</summary>
    public IReadOnlyList<string> DllTargets { get; }

    /// <summary>Major version of the game's Streamline, when its version strings say it.</summary>
    public int? Streamline { get; }

    public bool AntiCheat { get; }

    /// <summary>Another tool's upscaler sits beside the exe.</summary>
    public bool Foreign { get; }

    public ForeignIdentity? ForeignIdentity { get; }
}

public sealed class ForeignIdentity
{
    public ForeignIdentity(string engine, string variant, IReadOnlyList<string> evidence, bool manifestError)
    {
        Engine = engine;
        Variant = variant;
        Evidence = evidence;
        ManifestError = manifestError;
    }

    /// <summary><c>helixsr</c>, <c>optiscaler</c> or <c>unknown</c>.</summary>
    public string Engine { get; }

    /// <summary><c>dlss</c>, <c>fsr</c> or <c>unknown</c>.</summary>
    public string Variant { get; }

    public IReadOnlyList<string> Evidence { get; }

    public bool ManifestError { get; }
}
