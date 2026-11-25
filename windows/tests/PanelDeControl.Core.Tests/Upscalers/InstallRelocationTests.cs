using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class InstallRelocationTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-relocation-" + Guid.NewGuid().ToString("N"));

    public InstallRelocationTests()
    {
        Directory.CreateDirectory(_root);
    }

    public void Dispose() => Directory.Delete(_root, true);

    private string Game(string library, string name = "Plain")
    {
        var folder = Path.Combine(_root, library, "steamapps", "common", name);
        Directory.CreateDirectory(Path.Combine(folder, "Binaries", "Win64"));
        return folder;
    }

    [Fact]
    public void AMovedGameFolderMapsTheTargetAndHelixPathsToTheCurrentOne()
    {
        var oldGame = Path.Combine(_root, "old", "steamapps", "common", "Plain");
        var game = Game("new");
        File.WriteAllText(Path.Combine(game, "Binaries", "Win64", "helixsr.log"), "x");
        File.WriteAllText(Path.Combine(game, "Binaries", "Win64", "record.json"), "x");
        var install = new InstalledUpscaler
        {
            Target = Path.Combine(oldGame, "Binaries", "Win64"),
            ExeFolder = Path.Combine(oldGame, "Binaries", "Win64"),
            Log = Path.Combine(oldGame, "Binaries", "Win64", "helixsr.log"),
            HelixFile = Path.Combine(oldGame, "Binaries", "Win64", "record.json"),
        };

        InstallRelocation.Apply(install, game);

        var target = Path.Combine(game, "Binaries", "Win64");
        Assert.Equal((target, target, Path.Combine(target, "helixsr.log"), Path.Combine(target, "record.json")),
            (install.Target, install.ExeFolder, install.Log, install.HelixFile));
    }

    [Fact]
    public void AGameWhoseFolderDidNotMoveKeepsEveryPathAndASameNamedSubfolderIsNotTheGameFolder()
    {
        var game = Game("lib", "Foo");
        var inner = Path.Combine(game, "Foo", "Binaries", "Win64");
        Directory.CreateDirectory(inner);
        var install = new InstalledUpscaler { Target = inner };

        InstallRelocation.Apply(install, game);

        Assert.Equal(inner, install.Target);
        var oldInner = Path.Combine(_root, "old", "steamapps", "common", "Foo", "Foo", "Binaries", "Win64");
        Assert.Equal(inner, InstallRelocation.Relocated(oldInner, oldInner, game));
    }

    [Fact]
    public void APathTheNewFolderLacksStaysWhereItWas()
    {
        var game = Path.Combine(_root, "new", "steamapps", "common", "Plain");
        Directory.CreateDirectory(game);
        var gone = Path.Combine(_root, "old", "steamapps", "common", "Plain", "Binaries", "Win64");
        Directory.CreateDirectory(gone);
        var install = new InstalledUpscaler { Target = gone };

        InstallRelocation.Apply(install, game);

        Assert.Equal(gone, install.Target);
    }

    [Theory]
    [InlineData("Game.exe", "Game.exe")]
    [InlineData("Binaries/Win64/Game.EXE", "Binaries/Win64/Game.EXE")]
    [InlineData(@"Binaries\Win64\Game.exe", "Binaries/Win64/Game.exe")]
    [InlineData("a/../Game.exe", "Game.exe")]
    [InlineData("../Game.exe", null)]
    [InlineData("a/../../Game.exe", null)]
    [InlineData("Game.dll", null)]
    [InlineData("", null)]
    [InlineData("Game.exe:stream", null)]
    [InlineData("Bin/", null)]
    public void OnlyAnExeInsideTheGameFolderIsAccepted(string exe, string? expected)
    {
        Assert.Equal(expected, ExeOverride.Relative(Path.Combine(_root, "Game"), exe));
    }

    [Fact]
    public void AnAbsoluteExeInsideTheFolderBecomesRelativeAndOneOutsideIsRefused()
    {
        var game = Path.Combine(_root, "Game");

        Assert.Equal("Bin/Game.exe", ExeOverride.Relative(game, Path.Combine(game, "Bin", "Game.exe")));
        Assert.Null(ExeOverride.Relative(game, Path.Combine(_root, "GameElse", "Game.exe")));
        Assert.Null(ExeOverride.Relative(game, Path.Combine(_root, "Game.exe")));
    }
}
