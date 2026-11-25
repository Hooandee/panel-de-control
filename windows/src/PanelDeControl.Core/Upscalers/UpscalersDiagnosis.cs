using System.Runtime.Serialization;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What Windows answers of Linux's <c>compatibility</c>: the upscaler inputs a game ships and the build Panel prefers for it.</summary>
[DataContract]
public sealed class UpscalerCompatEntry
{
    [DataMember(Name = "appid", Order = 1, IsRequired = true)]
    public string AppId { get; set; } = "";

    /// <summary>The input kinds the game's own files reveal (<c>dlss</c>, <c>fsr31</c>, ...).</summary>
    [DataMember(Name = "inputs", Order = 2, IsRequired = true)]
    public string[] Inputs { get; set; } = new string[0];

    [DataMember(Name = "preferred", Order = 3, EmitDefaultValue = false)]
    public string? Preferred { get; set; }
}

[DataContract]
public sealed class UpscalerCompat
{
    /// <summary>False when the scan budget ran out: the games left out were not looked at, not found without inputs.</summary>
    [DataMember(Name = "complete", Order = 1, IsRequired = true)]
    public bool Complete { get; set; } = true;

    /// <summary>Only games Panel found installed; the others are left out, as on Linux.</summary>
    [DataMember(Name = "games", Order = 2, IsRequired = true)]
    public UpscalerCompatEntry[] Games { get; set; } = new UpscalerCompatEntry[0];
}

[DataContract]
public sealed class UpscalerDiagnosisAction
{
    [DataMember(Name = "at", Order = 1, IsRequired = true)]
    public long At { get; set; }

    [DataMember(Name = "action", Order = 2, IsRequired = true)]
    public string Action { get; set; } = "";

    [DataMember(Name = "state", Order = 3, IsRequired = true)]
    public string State { get; set; } = "";

    [DataMember(Name = "build", Order = 4, EmitDefaultValue = false)]
    public string? Build { get; set; }

    [DataMember(Name = "error", Order = 5, EmitDefaultValue = false)]
    public string? Error { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisHistory
{
    [DataMember(Name = "build", Order = 1, IsRequired = true)]
    public string Build { get; set; } = "";

    [DataMember(Name = "proxy", Order = 2, EmitDefaultValue = false)]
    public string? Proxy { get; set; }

    [DataMember(Name = "at", Order = 3, IsRequired = true)]
    public long At { get; set; }

    [DataMember(Name = "result", Order = 4, IsRequired = true)]
    public string Result { get; set; } = "";

    [DataMember(Name = "observed", Order = 5, EmitDefaultValue = false)]
    public string? Observed { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisComponent
{
    [DataMember(Name = "id", Order = 1, IsRequired = true)]
    public string Id { get; set; } = "";

    /// <summary>In groups of four characters, as the Linux report writes it.</summary>
    [DataMember(Name = "sha256", Order = 2, IsRequired = true)]
    public string Sha256 { get; set; } = "";
}

[DataContract]
public sealed class UpscalerDiagnosisInstall
{
    [DataMember(Name = "build", Order = 1, IsRequired = true)]
    public string Build { get; set; } = "";

    [DataMember(Name = "engine", Order = 2, IsRequired = true)]
    public string Engine { get; set; } = "";

    [DataMember(Name = "archive", Order = 3, EmitDefaultValue = false)]
    public string? Archive { get; set; }

    [DataMember(Name = "proxy", Order = 4, EmitDefaultValue = false)]
    public string? Proxy { get; set; }

    [DataMember(Name = "installed_at", Order = 5, IsRequired = true)]
    public long InstalledAt { get; set; }

    [DataMember(Name = "verification_since", Order = 6, EmitDefaultValue = false)]
    public long? VerificationSince { get; set; }

    [DataMember(Name = "options", Order = 7, EmitDefaultValue = false)]
    public UpscalerOptions? Options { get; set; }

    [DataMember(Name = "components", Order = 8, IsRequired = true)]
    public UpscalerDiagnosisComponent[] Components { get; set; } = new UpscalerDiagnosisComponent[0];

    /// <summary>The arguments the recipe asks for and the ones Panel put in Steam.</summary>
    [DataMember(Name = "args", Order = 9, EmitDefaultValue = false)]
    public string[]? Args { get; set; }

    [DataMember(Name = "added_args", Order = 10, EmitDefaultValue = false)]
    public string[]? AddedArgs { get; set; }

    [DataMember(Name = "anr", Order = 11, EmitDefaultValue = false)]
    public bool? Anr { get; set; }

    /// <summary>Whether the files the install lists are all in the game folder.</summary>
    [DataMember(Name = "installed", Order = 12, IsRequired = true)]
    public bool Installed { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisManifest
{
    [DataMember(Name = "present", Order = 1, IsRequired = true)]
    public bool Present { get; set; }

    [DataMember(Name = "complete", Order = 2, EmitDefaultValue = false)]
    public bool? Complete { get; set; }

    [DataMember(Name = "files", Order = 3, EmitDefaultValue = false)]
    public int? Files { get; set; }

    /// <summary>Relative to the folder the install went in, never absolute.</summary>
    [DataMember(Name = "missing", Order = 4, EmitDefaultValue = false)]
    public string[]? Missing { get; set; }

    [DataMember(Name = "changed", Order = 5, EmitDefaultValue = false)]
    public string[]? Changed { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisIni
{
    /// <summary>True when there is no OptiScaler.ini to read.</summary>
    [DataMember(Name = "missing", Order = 1, EmitDefaultValue = false)]
    public bool? Missing { get; set; }

    [DataMember(Name = "values", Order = 2, IsRequired = true)]
    public UpscalerIniEdit[] Values { get; set; } = new UpscalerIniEdit[0];
}

[DataContract]
public sealed class UpscalerDiagnosisIniChange
{
    [DataMember(Name = "key", Order = 1, IsRequired = true)]
    public string Key { get; set; } = "";

    /// <summary>What Panel wrote.</summary>
    [DataMember(Name = "panel", Order = 2, IsRequired = true)]
    public string Panel { get; set; } = "";

    /// <summary>What the file holds now; absent when the key is gone.</summary>
    [DataMember(Name = "now", Order = 3, EmitDefaultValue = false)]
    public string? Now { get; set; }
}

/// <summary>Keys changed in OptiScaler.ini since Panel wrote it, as Linux's <c>ini_drift</c> says it.</summary>
[DataContract]
public sealed class UpscalerDiagnosisIniDrift
{
    /// <summary><c>unrecorded</c>, <c>missing</c>, <c>changed</c> or <c>as_written</c>.</summary>
    [DataMember(Name = "status", Order = 1, IsRequired = true)]
    public string Status { get; set; } = IniDrift.Unrecorded;

    [DataMember(Name = "written_at", Order = 2, EmitDefaultValue = false)]
    public double? WrittenAt { get; set; }

    [DataMember(Name = "modified_at", Order = 3, EmitDefaultValue = false)]
    public double? ModifiedAt { get; set; }

    [DataMember(Name = "keys", Order = 4, EmitDefaultValue = false)]
    public UpscalerDiagnosisIniChange[]? Keys { get; set; }

    public static UpscalerDiagnosisIniDrift From(IniDrift drift) => new()
    {
        Status = drift.Status,
        WrittenAt = drift.WrittenAt,
        ModifiedAt = drift.ModifiedAt,
        Keys = drift.Status is IniDrift.Changed or IniDrift.AsWritten
            ? drift.Keys.Select(change => new UpscalerDiagnosisIniChange { Key = change.Key, Panel = change.Panel, Now = change.Now }).ToArray()
            : null,
    };
}

/// <summary>A key the user edited by hand: the value only when it is a number, a switch or one of the key's own choices.</summary>
[DataContract]
public sealed class UpscalerDiagnosisEdit
{
    [DataMember(Name = "key", Order = 1, IsRequired = true)]
    public string Key { get; set; } = "";

    [DataMember(Name = "value", Order = 2, EmitDefaultValue = false)]
    public string? Value { get; set; }

    [DataMember(Name = "value_omitted", Order = 3, EmitDefaultValue = false)]
    public bool? ValueOmitted { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisLog
{
    [DataMember(Name = "present", Order = 1, IsRequired = true)]
    public bool Present { get; set; }

    [DataMember(Name = "stale", Order = 2, EmitDefaultValue = false)]
    public bool? Stale { get; set; }

    [DataMember(Name = "version", Order = 3, EmitDefaultValue = false)]
    public string? Version { get; set; }

    [DataMember(Name = "upscaler", Order = 4, EmitDefaultValue = false)]
    public string? Upscaler { get; set; }

    [DataMember(Name = "input", Order = 5, EmitDefaultValue = false)]
    public string? Input { get; set; }

    [DataMember(Name = "fg", Order = 6, EmitDefaultValue = false)]
    public string? FrameGen { get; set; }

    [DataMember(Name = "fg_state", Order = 7, EmitDefaultValue = false)]
    public string? FrameGenState { get; set; }

    [DataMember(Name = "fsr4_model", Order = 8, EmitDefaultValue = false)]
    public string? Fsr4Model { get; set; }

    /// <summary>The FSR 4 library that answered, with its version and model.</summary>
    [DataMember(Name = "provider", Order = 9, EmitDefaultValue = false)]
    public string? Provider { get; set; }

    [DataMember(Name = "fallback", Order = 10, EmitDefaultValue = false)]
    public string? Fallback { get; set; }

    [DataMember(Name = "texture_failure", Order = 11, EmitDefaultValue = false)]
    public bool? TextureFailure { get; set; }

    [DataMember(Name = "errors", Order = 12, EmitDefaultValue = false)]
    public int? Errors { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisSolution
{
    [DataMember(Name = "effective_api", Order = 1, EmitDefaultValue = false)]
    public string? EffectiveApi { get; set; }

    /// <summary><c>recipe</c>, <c>detected</c> or <c>unknown</c>.</summary>
    [DataMember(Name = "api_source", Order = 2, IsRequired = true)]
    public string ApiSource { get; set; } = "unknown";

    [DataMember(Name = "quality_owner", Order = 3, IsRequired = true)]
    public string QualityOwner { get; set; } = "panel";

    [DataMember(Name = "recipe_revision", Order = 4, EmitDefaultValue = false)]
    public int? RecipeRevision { get; set; }

    [DataMember(Name = "recommended_input", Order = 5, EmitDefaultValue = false)]
    public string? RecommendedInput { get; set; }

    [DataMember(Name = "input_reconciled", Order = 6, IsRequired = true)]
    public bool InputReconciled { get; set; }

    [DataMember(Name = "warning_reason", Order = 7, EmitDefaultValue = false)]
    public string? WarningReason { get; set; }

    [DataMember(Name = "dependencies", Order = 8, EmitDefaultValue = false)]
    public string[]? Dependencies { get; set; }

    /// <summary>The frame generation route the plan takes and the ones it offers.</summary>
    [DataMember(Name = "fg_route", Order = 9, EmitDefaultValue = false)]
    public string? FrameGenRoute { get; set; }

    [DataMember(Name = "fg_routes", Order = 10, EmitDefaultValue = false)]
    public string[]? FrameGenRoutes { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisRecipe
{
    [DataMember(Name = "appid", Order = 1, IsRequired = true)]
    public string AppId { get; set; } = "";

    [DataMember(Name = "status", Order = 2, IsRequired = true)]
    public string Status { get; set; } = "";

    [DataMember(Name = "revision", Order = 3, IsRequired = true)]
    public long Revision { get; set; }

    [DataMember(Name = "installable", Order = 4, IsRequired = true)]
    public bool Installable { get; set; }

    [DataMember(Name = "dependencies", Order = 5, EmitDefaultValue = false)]
    public string[]? Dependencies { get; set; }

    [DataMember(Name = "required_args", Order = 6, EmitDefaultValue = false)]
    public string[]? RequiredArgs { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisLoader
{
    /// <summary>Relative to the game folder.</summary>
    [DataMember(Name = "path", Order = 1, IsRequired = true)]
    public string Path { get; set; } = "";

    [DataMember(Name = "dir", Order = 2, IsRequired = true)]
    public bool Directory { get; set; }

    /// <summary><c>panel</c> when the install's manifest lists it, else <c>other</c>.</summary>
    [DataMember(Name = "owner", Order = 3, IsRequired = true)]
    public string Owner { get; set; } = "other";
}

[DataContract]
public sealed class UpscalerDiagnosisGameFiles
{
    [DataMember(Name = "loaders", Order = 1, IsRequired = true)]
    public UpscalerDiagnosisLoader[] Loaders { get; set; } = new UpscalerDiagnosisLoader[0];

    /// <summary>Files that replace Steam's own API layer, reported as found and never interpreted.</summary>
    [DataMember(Name = "store_files", Order = 2, IsRequired = true)]
    public string[] StoreFiles { get; set; } = new string[0];

    [DataMember(Name = "anti_cheat", Order = 3, IsRequired = true)]
    public bool AntiCheat { get; set; }

    [DataMember(Name = "apis", Order = 4, IsRequired = true)]
    public string[] Apis { get; set; } = new string[0];
}

[DataContract]
public sealed class UpscalerDiagnosisSteam
{
    /// <summary>Steam libraries Panel found.</summary>
    [DataMember(Name = "libraries", Order = 1, IsRequired = true)]
    public int Libraries { get; set; }

    /// <summary>The game's appmanifest was found in one of them.</summary>
    [DataMember(Name = "found", Order = 2, IsRequired = true)]
    public bool Found { get; set; }
}

[DataContract]
public sealed class UpscalerDiagnosisMod
{
    [DataMember(Name = "count", Order = 1, IsRequired = true)]
    public int Count { get; set; }

    [DataMember(Name = "applied", Order = 2, IsRequired = true)]
    public bool Applied { get; set; }
}

/// <summary>
/// The per-game support report, with the keys of Linux's <c>diagnose</c> where Windows has the data: install facts,
/// manifest, log verdict, image settings, solution, Steam lookup and the OptiScaler.ini Panel wrote against what it holds now.
/// </summary>
[DataContract]
public sealed class UpscalerDiagnosis
{
    public const int MaximumActions = 20;
    public const int MaximumHistory = 8;
    public const int MaximumNames = 40;
    public const int MaximumExcerpt = 60;
    public const int ExcerptLine = 220;

    [DataMember(Name = "appid", Order = 1, IsRequired = true)]
    public string AppId { get; set; } = "";

    [DataMember(Name = "name", Order = 2, EmitDefaultValue = false)]
    public string? Name { get; set; }

    [DataMember(Name = "state_flags", Order = 3, EmitDefaultValue = false)]
    public long? StateFlags { get; set; }

    [DataMember(Name = "build_id", Order = 4, EmitDefaultValue = false)]
    public string? BuildId { get; set; }

    [DataMember(Name = "manual_exe_selected", Order = 5, IsRequired = true)]
    public bool ManualExeSelected { get; set; }

    [DataMember(Name = "steam_lookup", Order = 6, IsRequired = true)]
    public UpscalerDiagnosisSteam SteamLookup { get; set; } = new();

    [DataMember(Name = "actions", Order = 7, IsRequired = true)]
    public UpscalerDiagnosisAction[] Actions { get; set; } = new UpscalerDiagnosisAction[0];

    [DataMember(Name = "history", Order = 8, IsRequired = true)]
    public UpscalerDiagnosisHistory[] History { get; set; } = new UpscalerDiagnosisHistory[0];

    [DataMember(Name = "install", Order = 9, EmitDefaultValue = false)]
    public UpscalerDiagnosisInstall? Install { get; set; }

    [DataMember(Name = "manifest", Order = 10, EmitDefaultValue = false)]
    public UpscalerDiagnosisManifest? Manifest { get; set; }

    [DataMember(Name = "ini", Order = 11, EmitDefaultValue = false)]
    public UpscalerDiagnosisIni? Ini { get; set; }

    [DataMember(Name = "ini_drift", Order = 12, EmitDefaultValue = false)]
    public UpscalerDiagnosisIniDrift? IniDrift { get; set; }

    /// <summary>The keys the user edited by hand.</summary>
    [DataMember(Name = "advanced", Order = 13, EmitDefaultValue = false)]
    public UpscalerDiagnosisEdit[]? Advanced { get; set; }

    /// <summary>What the log says since the install; <c>unverifiable</c> for an install with no log (DLL mode).</summary>
    [DataMember(Name = "log_verdict", Order = 14, EmitDefaultValue = false)]
    public string? LogVerdict { get; set; }

    [DataMember(Name = "log_facts", Order = 15, EmitDefaultValue = false)]
    public UpscalerDiagnosisLog? LogFacts { get; set; }

    [DataMember(Name = "log_excerpt", Order = 16, EmitDefaultValue = false)]
    public string[]? LogExcerpt { get; set; }

    [DataMember(Name = "image_settings", Order = 17, EmitDefaultValue = false)]
    public UpscalerImageSettings? ImageSettings { get; set; }

    /// <summary>What the plan for the installed build would be on this game now.</summary>
    [DataMember(Name = "current_solution", Order = 18, EmitDefaultValue = false)]
    public UpscalerDiagnosisSolution? CurrentSolution { get; set; }

    [DataMember(Name = "recipe", Order = 19, EmitDefaultValue = false)]
    public UpscalerDiagnosisRecipe? Recipe { get; set; }

    [DataMember(Name = "mod", Order = 20, EmitDefaultValue = false)]
    public UpscalerDiagnosisMod? Mod { get; set; }

    [DataMember(Name = "game_files", Order = 21, EmitDefaultValue = false)]
    public UpscalerDiagnosisGameFiles? GameFiles { get; set; }

    [DataMember(Name = "foreign", Order = 22, EmitDefaultValue = false)]
    public UpscalerForeignSummary? Foreign { get; set; }
}
