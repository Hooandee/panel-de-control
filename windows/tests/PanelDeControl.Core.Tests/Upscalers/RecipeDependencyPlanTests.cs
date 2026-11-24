using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class RecipeDependencyPlanTests
{
    private static readonly RecipeCatalog Catalog = Load();

    [Theory]
    [InlineData("14.40.33810.0", RedistState.Satisfied)]
    [InlineData("14.51.36247.00", RedistState.Satisfied)]
    [InlineData("v14.40.33810", RedistState.Satisfied)]
    [InlineData("15.0", RedistState.Satisfied)]
    [InlineData("14.9.99999.0", RedistState.Outdated)]
    [InlineData("14.40.33809.0", RedistState.Outdated)]
    [InlineData("14.39", RedistState.Outdated)]
    [InlineData("", RedistState.Missing)]
    [InlineData("garbage", RedistState.Missing)]
    [InlineData(null, RedistState.Missing)]
    public void RedistVersionIsComparedNumerically(string? installed, RedistState expected)
    {
        var status = WindowsRedistStatus.Evaluate(Catalog.Dependencies["vc-redist-x64"], installed);
        Assert.Equal(expected, status.State);
        Assert.Equal("14.40.33810.0", status.RequiredVersion);
    }

    [Fact]
    public void CompareTreatsMissingComponentsAsZero()
    {
        Assert.Equal(0, WindowsRedistStatus.Compare("14.40", "14.40.0.0"));
        Assert.True(WindowsRedistStatus.Compare("14.100", "14.20") > 0);
    }

    [Theory]
    [InlineData("1462040")]
    [InlineData("1687950")]
    public void OutdatedRedistWarnsWithTheMicrosoftPageAndKeepsTheInstall(string appId)
    {
        var plan = RecipeDependencyPlan.Build(Catalog, Recipe(appId), _ => "14.30.30708.0");

        Assert.Equal(new[] { "vc-redist-x64", "luma-" + (appId == "1462040" ? "ff7" : "p5r") }, plan.Entries.Select(entry => entry.Id).Where(id => !id.StartsWith("vcrun") && !id.StartsWith("msvcrt")));
        var redist = plan.Entries.Single(entry => entry.Id == "vc-redist-x64");
        Assert.Equal(DependencyOutcome.RedistOutdated, redist.Outcome);
        Assert.Equal("14.30.30708.0", redist.InstalledVersion);
        Assert.Equal("14.40.33810.0", redist.RequiredVersion);
        Assert.Equal("https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist", redist.Url);
        Assert.True(plan.HasWarnings);
        Assert.Equal(DependencyOutcome.InstallFromAsset, plan.Entries.Single(entry => entry.Kind == "game_files").Outcome);
    }

    [Fact]
    public void MissingRedistWarns()
    {
        var plan = RecipeDependencyPlan.Build(Catalog, Recipe("1462040"), _ => null);

        var redist = plan.Entries.Single(entry => entry.Id == "vc-redist-x64");
        Assert.Equal(DependencyOutcome.RedistMissing, redist.Outcome);
        Assert.Null(redist.InstalledVersion);
        Assert.True(redist.Warns);
    }

    [Fact]
    public void SatisfiedRedistDoesNotWarn()
    {
        var plan = RecipeDependencyPlan.Build(Catalog, Recipe("1687950"), component => component == "vc14_x64" ? "14.51.36247.00" : null);

        Assert.Equal(DependencyOutcome.RedistSatisfied, plan.Entries.Single(entry => entry.Id == "vc-redist-x64").Outcome);
        Assert.False(plan.HasWarnings);
    }

    [Fact]
    public void ProtonDependenciesAreNotApplicableOnWindows()
    {
        var plan = RecipeDependencyPlan.Build(Catalog, Recipe("1462040"), _ => "14.51.36247.00");

        foreach (var entry in plan.Entries.Where(entry => entry.Kind == "proton_dependency"))
        {
            Assert.Equal(DependencyOutcome.NotApplicable, entry.Outcome);
            Assert.False(entry.Warns);
        }
    }

    [Fact]
    public void RedistComesBeforeTheFilesThatNeedIt()
    {
        var ids = RecipeDependencyPlan.Build(Catalog, Recipe("1462040"), _ => null).Entries.Select(entry => entry.Id).ToList();

        Assert.True(ids.IndexOf("vc-redist-x64") < ids.IndexOf("luma-ff7"));
    }

    [Fact]
    public void UserFilesNeedTheUserUntilProvidedAndThenAreJudgedByVersion()
    {
        var dependency = Catalog.Dependencies["puredark-upscaler-base"];

        Assert.Equal(DependencyOutcome.UserFileReady, RecipeDependencyPlan.UserFileOutcome(dependency, "1.1.2"));
        Assert.Equal(DependencyOutcome.UserFileOtherVersion, RecipeDependencyPlan.UserFileOutcome(dependency, "1.1.0"));
        Assert.Equal(DependencyOutcome.UserFileAvoid, RecipeDependencyPlan.UserFileOutcome(dependency, "1.2.0"));
        Assert.Equal(DependencyOutcome.UserFileReady, RecipeDependencyPlan.UserFileOutcome(dependency, null));

        var recipe = Catalog.Games.Values.SelectMany(game => game.Recipes.Values).First(candidate => candidate.Dependencies.Contains("puredark-upscaler-base"));
        var missing = RecipeDependencyPlan.Build(Catalog, recipe, _ => "14.51.36247.00").Entries.Single(entry => entry.Id == "puredark-upscaler-base");
        Assert.Equal(DependencyOutcome.NeedsUserFile, missing.Outcome);
        Assert.Equal("https://www.nexusmods.com/site/mods/502?tab=files&file_id=2293", missing.Url);

        var provided = RecipeDependencyPlan.Build(Catalog, recipe, _ => "14.51.36247.00",
            new Dictionary<string, string?> { ["puredark-upscaler-base"] = "1.2.0" }).Entries.Single(entry => entry.Id == "puredark-upscaler-base");
        Assert.Equal(DependencyOutcome.UserFileAvoid, provided.Outcome);
        Assert.Equal("1.2.0", provided.InstalledVersion);
    }

    private static GameRecipe Recipe(string appId) => Catalog.Match(appId, "optiscaler", "windows", "amd64")!;

    private static RecipeCatalog Load()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "Data", "GameRecipes");
        return RecipeCatalog.Load(Directory.EnumerateFiles(root, "*.json", SearchOption.AllDirectories)
            .Where(path => !Path.GetFileName(path).Equals("schema.json", StringComparison.Ordinal))
            .ToDictionary(path => Path.GetRelativePath(root, path).Replace('\\', '/'), File.ReadAllBytes, StringComparer.Ordinal));
    }
}
