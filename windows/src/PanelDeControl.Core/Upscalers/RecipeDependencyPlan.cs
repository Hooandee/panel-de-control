namespace PanelDeControl.Core.Upscalers;

public enum DependencyOutcome
{
    InstallFromAsset,
    RedistSatisfied,
    RedistMissing,
    RedistOutdated,
    NotApplicable,
    NeedsUserFile,
    UserFileReady,
    UserFileOtherVersion,
    UserFileAvoid,
}

public sealed class DependencyPlanEntry
{
    internal DependencyPlanEntry(RecipeDependency dependency, DependencyOutcome outcome, string? installedVersion, string? requiredVersion, string? url)
    {
        Id = dependency.Id;
        Kind = dependency.Kind;
        Name = dependency.Name;
        Outcome = outcome;
        InstalledVersion = installedVersion;
        RequiredVersion = requiredVersion;
        Url = url;
    }

    public string Id { get; }

    public string Kind { get; }

    public string? Name { get; }

    public DependencyOutcome Outcome { get; }

    public string? InstalledVersion { get; }

    public string? RequiredVersion { get; }

    /// <summary>Where the user gets what is missing: Microsoft's page for a redistributable, the mod page for a user file.</summary>
    public string? Url { get; }

    /// <summary>True when the user should hear about it. Never a veto: the install goes ahead either way.</summary>
    public bool Warns => Outcome is DependencyOutcome.RedistMissing or DependencyOutcome.RedistOutdated or DependencyOutcome.NeedsUserFile
        or DependencyOutcome.UserFileOtherVersion or DependencyOutcome.UserFileAvoid;
}

/// <summary>What Windows does about each dependency of a matched recipe, in install order. Warns, never blocks.</summary>
public sealed class RecipeDependencyPlan
{
    private RecipeDependencyPlan(IReadOnlyList<DependencyPlanEntry> entries)
    {
        Entries = entries;
    }

    public IReadOnlyList<DependencyPlanEntry> Entries { get; }

    public bool HasWarnings => Entries.Any(entry => entry.Warns);

    /// <param name="installedRedist">Installed version of a runtime component (<c>vc14_x64</c>), or null when absent.</param>
    /// <param name="userFileVersions">Version of the file the user already provided, by dependency id; a null version means provided but unversioned.</param>
    public static RecipeDependencyPlan Build(RecipeCatalog catalog, GameRecipe recipe, Func<string, string?> installedRedist,
        IReadOnlyDictionary<string, string?>? userFileVersions = null)
    {
        var entries = new List<DependencyPlanEntry>();
        foreach (var dependency in catalog.DependencyOrder(recipe.Dependencies))
        {
            entries.Add(dependency.Kind switch
            {
                "game_files" => new DependencyPlanEntry(dependency, DependencyOutcome.InstallFromAsset, null, null, null),
                "windows_redist" => Redist(dependency, installedRedist),
                "user_files" => UserFile(dependency, userFileVersions),
                _ => new DependencyPlanEntry(dependency, DependencyOutcome.NotApplicable, null, null, null),
            });
        }
        return new RecipeDependencyPlan(entries);
    }

    /// <summary>The state check of <c>user_deps.py</c>: the file the user gave, judged by its version.</summary>
    public static DependencyOutcome UserFileOutcome(RecipeDependency dependency, string? version)
    {
        if (version is not null && dependency.AvoidVersions.Contains(version))
        {
            return DependencyOutcome.UserFileAvoid;
        }
        return version is not null && dependency.Version is not null && version != dependency.Version
            ? DependencyOutcome.UserFileOtherVersion
            : DependencyOutcome.UserFileReady;
    }

    private static DependencyPlanEntry Redist(RecipeDependency dependency, Func<string, string?> installedRedist)
    {
        var status = WindowsRedistStatus.Evaluate(dependency, installedRedist(dependency.Verb ?? ""));
        var outcome = status.State switch
        {
            RedistState.Satisfied => DependencyOutcome.RedistSatisfied,
            RedistState.Outdated => DependencyOutcome.RedistOutdated,
            _ => DependencyOutcome.RedistMissing,
        };
        return new DependencyPlanEntry(dependency, outcome, status.InstalledVersion, status.RequiredVersion,
            outcome == DependencyOutcome.RedistSatisfied ? null : dependency.PageUrl);
    }

    private static DependencyPlanEntry UserFile(RecipeDependency dependency, IReadOnlyDictionary<string, string?>? userFileVersions)
    {
        var url = dependency.DownloadUrl ?? dependency.PageUrl;
        if (userFileVersions is null || !userFileVersions.TryGetValue(dependency.Id, out var version))
        {
            return new DependencyPlanEntry(dependency, DependencyOutcome.NeedsUserFile, null, dependency.Version, url);
        }
        return new DependencyPlanEntry(dependency, UserFileOutcome(dependency, version), version, dependency.Version, url);
    }
}
