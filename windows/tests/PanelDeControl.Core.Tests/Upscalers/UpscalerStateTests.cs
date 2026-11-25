using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class UpscalerStateTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-upscaler-state-" + Guid.NewGuid().ToString("N"));

    public UpscalerStateTests()
    {
        Directory.CreateDirectory(_root);
    }

    public void Dispose() => Directory.Delete(_root, true);

    private string StatePath => Path.Combine(_root, "upscalers", "state.json");

    [Fact]
    public void AnInstallSurvivesARestart()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1245620", Sample("fsr-3.1", Path.Combine(_root, "Game")), 1700000000.5);
        store.Record(new UpscalerAction(1700000001, "1245620", "install", "done", "fsr-3.1"));

        var reopened = new UpscalerStateStore(StatePath);

        var stored = reopened.Install("1245620")!;
        Assert.Equal(1700000000.5, stored.InstalledAt);
        Assert.Equal(("fsr-3.1", "optiscaler-0.9.4", "optiscaler", "dxgi.dll", "Binaries/Win64/Game.exe"),
            (stored.Install.Build, stored.Install.Archive, stored.Install.Engine, stored.Install.Proxy, stored.Install.Exe));
        Assert.Equal(Path.Combine(_root, "Game"), stored.Install.Target);
        Assert.Equal(("performance", "int8"), (stored.Install.Options.Quality, stored.Install.Options.Model));
        Assert.Equal(new[] { "FrameGen.Enabled" }, stored.Install.Managed);
        Assert.Equal("abc", Assert.Single(stored.Install.Components).Value);
        Assert.Equal("done", Assert.Single(reopened.Actions("1245620")).State);
    }

    [Fact]
    public void TheFileUsesTheLinuxFieldNames()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("7", Sample("fsr-3.1", _root), 5);

        var text = File.ReadAllText(StatePath);

        foreach (var field in new[] { "\"games\"", "\"install\"", "\"build\"", "\"archive\"", "\"engine\"", "\"proxy\"", "\"target\"", "\"exe\"",
                     "\"installed_at\"", "\"options\"", "\"components\"", "\"managed\"", "\"actions\"" })
        {
            Assert.Contains(field, text);
        }
    }

    [Fact]
    public void WritesGoThroughATemporaryFileThatNeverStays()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1", Sample("a", _root), 1);
        store.SetInstall("2", Sample("b", _root), 2);

        Assert.False(File.Exists(StatePath + ".tmp"));
        Assert.Equal(new[] { "1", "2" }, new UpscalerStateStore(StatePath).InstalledAppIds);
    }

    [Fact]
    public void AFailedReplaceLeavesTheFileAndTheMemoryAsTheyWere()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1", Sample("a", _root), 1);
        var before = File.ReadAllText(StatePath);
        var broken = new UpscalerStateStore(StatePath, (_, _) => throw new IOException("disk full"));

        Assert.Throws<IOException>(() => broken.SetInstall("2", Sample("b", _root), 2));

        Assert.Equal(before, File.ReadAllText(StatePath));
        Assert.False(File.Exists(StatePath + ".tmp"));
        Assert.Equal(new[] { "1" }, broken.InstalledAppIds);
    }

    [Fact]
    public void AStaleTemporaryFileDoesNotGetInTheWay()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(StatePath)!);
        File.WriteAllText(StatePath + ".tmp", "half a file {");

        new UpscalerStateStore(StatePath).SetInstall("1", Sample("a", _root), 1);

        Assert.Equal("a", new UpscalerStateStore(StatePath).Install("1")!.Install.Build);
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("{\"games\": {\"1\": {\"install\": {\"build\": \"x\"}}}}")]
    public void AnUnreadableFileStartsEmpty(string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(StatePath)!);
        File.WriteAllText(StatePath, content);

        Assert.Empty(new UpscalerStateStore(StatePath).InstalledAppIds);
    }

    [Fact]
    public void TheJournalKeepsTheLastTwentyPerGame()
    {
        var store = new UpscalerStateStore(StatePath);
        for (var index = 0; index < 25; index++)
        {
            store.Record(new UpscalerAction(index, "1", "install", "done", "a"));
        }

        var kept = new UpscalerStateStore(StatePath).Actions("1");

        Assert.Equal(UpscalerStateStore.ActionLimit, kept.Count);
        Assert.Equal(5, kept[0].At);
        Assert.Equal(24, kept[^1].At);
    }

    [Fact]
    public void ARemovedInstallIsForgotten()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1", Sample("a", _root), 1);
        store.ClearInstall("1");

        Assert.Null(new UpscalerStateStore(StatePath).Install("1"));
    }

    [Fact]
    public void WithoutAManifestTheInstallIsNotThere()
    {
        var game = Path.Combine(_root, "Game");
        Directory.CreateDirectory(game);

        Assert.False(ManifestCheck.Presence(game).Installed);

        WriteManifest(game, incomplete: true);
        var half = ManifestCheck.Presence(game);
        Assert.True(half.Present);
        Assert.False(half.Installed);

        WriteManifest(game, incomplete: false);
        Assert.True(ManifestCheck.Presence(game).Installed);
    }

    [Fact]
    public void VerifyCountsChangedAndMissingFiles()
    {
        var game = Path.Combine(_root, "Game");
        Directory.CreateDirectory(game);
        File.WriteAllText(Path.Combine(game, "dxgi.dll"), "ours");
        File.WriteAllText(Path.Combine(game, "OptiScaler.ini"), "ini");
        var hash = GameFiles.Sha256(Path.Combine(game, "dxgi.dll"));
        Directory.CreateDirectory(Path.Combine(game, GameManifest.Folder));
        File.WriteAllText(Path.Combine(game, GameManifest.Folder, GameManifest.FileName),
            "{\"files\": {\"dxgi.dll\": \"" + hash + "\", \"OptiScaler.ini\": null, \"gone.dll\": \"" + hash + "\"}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": []}");

        var intact = ManifestCheck.Verify(game);
        Assert.Equal((3, 0), (intact.Files, intact.Changed.Count));
        Assert.Equal(new[] { "gone.dll" }, intact.Missing);

        File.WriteAllText(Path.Combine(game, "dxgi.dll"), "replaced by the game");
        Assert.Equal(new[] { "dxgi.dll" }, ManifestCheck.Verify(game).Changed);
    }

    [Fact]
    public void RunningMeansAnImageInsideTheGameFolder()
    {
        var root = Path.Combine(_root, "steamapps", "common", "Game");

        Assert.True(GameGuards.IsRunningUnder(root, new[] { Path.Combine(root, "Binaries", "Win64", "Game.exe") }));
        Assert.True(GameGuards.IsRunningUnder(root.ToUpperInvariant(), new[] { Path.Combine(root, "Game.exe") }));
        Assert.False(GameGuards.IsRunningUnder(root, new[] { Path.Combine(_root, "steamapps", "common", "Game2", "Game.exe") }));
        Assert.False(GameGuards.IsRunningUnder(root, new[] { @"C:\Windows\explorer.exe" }));
        Assert.False(GameGuards.IsRunningUnder(root, Array.Empty<string>()));
    }

    [Theory]
    [InlineData(4L, null)]
    [InlineData(1026L, "updating")]
    [InlineData(6L, "update_pending")]
    public void InstallWaitsForSteamToFinishUpdating(long flags, string? expected)
    {
        var app = new SteamApp("1", "Game", Path.Combine(_root, "Game"), flags, null);

        if (expected is null)
        {
            GameGuards.EnsureCanInstall(app, Array.Empty<string>());
        }
        else
        {
            Assert.Equal(expected, Assert.Throws<UpscalerException>(() => GameGuards.EnsureCanInstall(app, Array.Empty<string>())).Code);
        }
    }

    [Fact]
    public void ARunningGameRefusesBothDirections()
    {
        var app = new SteamApp("1", "Game", Path.Combine(_root, "Game"), 4, null);
        var images = new[] { Path.Combine(_root, "Game", "Game.exe") };

        Assert.Equal("running", Assert.Throws<UpscalerException>(() => GameGuards.EnsureCanInstall(app, images)).Code);
        Assert.Equal("running", Assert.Throws<UpscalerException>(() => GameGuards.EnsureClosed(app, images)).Code);
    }

    [Fact]
    public void OnlyOneJobRunsAtATime()
    {
        var jobs = new UpscalerJobTracker();
        var first = jobs.Begin("install", "1");

        Assert.Equal("busy", Assert.Throws<UpscalerException>(() => jobs.Begin("install", "2")).Code);

        jobs.Stage("download", 100);
        jobs.Progress(40);
        var running = jobs.Snapshot()!;
        Assert.Equal((first.Id, "download", 40L, 100L), (running.Id, running.Stage, running.DoneBytes, running.TotalBytes));

        jobs.Fail("running");
        Assert.Equal(("error", "running"), (jobs.Snapshot()!.State, jobs.Snapshot()!.Error));
        Assert.NotEqual(first.Id, jobs.Begin("uninstall", "2").Id);
    }

    [Fact]
    public void AChosenExeSurvivesARestartUnderTheLinuxKeyAndOutlivesTheInstall()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1245620", Sample("fsr-3.1", Path.Combine(_root, "Game")), 1700000000);
        store.SetExe("1245620", "Binaries/Win64/Game.exe");
        store.SetExe("77", "Other.exe");
        store.ClearInstall("1245620");

        var reopened = new UpscalerStateStore(StatePath);

        Assert.Equal(("Binaries/Win64/Game.exe", "Other.exe", null), (reopened.Exe("1245620"), reopened.Exe("77"), reopened.Exe("1")));
        Assert.Contains("\"exe\": \"Binaries/Win64/Game.exe\"", File.ReadAllText(StatePath));
        reopened.SetExe("1245620", null);
        Assert.Null(new UpscalerStateStore(StatePath).Exe("1245620"));
        Assert.Equal("Other.exe", new UpscalerStateStore(StatePath).Exe("77"));
    }

    [Fact]
    public void AForeignBackupSurvivesARestartUnderTheLinuxKeyAndRollsBackAFailedWrite()
    {
        var store = new UpscalerStateStore(StatePath);
        var backup = new ForeignBackup { Dir = Path.Combine(_root, "foreign", "1", "5"), Target = Path.Combine(_root, "Game"), Items = { "OptiScaler.ini" }, Swaps = { "dxgi.dll" }, At = 1700000000.5 };
        store.SetForeignBackup("1245620", backup);
        backup.Items.Add("changed after saving");

        var reopened = new UpscalerStateStore(StatePath).ForeignBackupOf("1245620")!;

        Assert.Equal((backup.Dir, backup.Target, 1700000000.5), (reopened.Dir, reopened.Target, reopened.At));
        Assert.Equal(new[] { "OptiScaler.ini" }, reopened.Items);
        Assert.Equal(new[] { "dxgi.dll" }, reopened.Swaps);
        Assert.Null(new UpscalerStateStore(StatePath).ForeignBackupOf("1"));
        Assert.Contains("\"foreign_backup\"", File.ReadAllText(StatePath));
        new UpscalerStateStore(StatePath).SetForeignBackup("1245620", null);
        Assert.Null(new UpscalerStateStore(StatePath).ForeignBackupOf("1245620"));

        var failing = new UpscalerStateStore(StatePath, (_, _) => throw new IOException("disk"));
        Assert.Throws<IOException>(() => failing.SetForeignBackup("9", backup));
        Assert.Null(failing.ForeignBackupOf("9"));
    }

    [Fact]
    public void HandEditsImageOverridesAndTheReceiptSurviveARestart()
    {
        var store = new UpscalerStateStore(StatePath);
        var install = Sample("fsr-3.1", Path.Combine(_root, "Game"));
        install.Edited = new[] { new KeyValuePair<string, string>("Menu.Scale", "1.5"), new KeyValuePair<string, string>("Log.LogLevel", "3") };
        install.ImageOverrides = new[] { new KeyValuePair<string, string>("CAS.Enabled", "true"), new KeyValuePair<string, string>("Sharpness.Sharpness", "0.25") };
        install.VerificationSince = 1700000123.25;
        store.SetInstall("1245620", install, 1700000000);
        var receipt = new ImageSettingsReceipt
        {
            Target = Path.Combine(_root, "Game", "OptiScaler.ini"),
            Original = new[] { new KeyValuePair<string, string>("CAS.Enabled", "auto"), new KeyValuePair<string, string>("Sharpness.Sharpness", "0.60") }.ToList(),
            Applied = new[] { new KeyValuePair<string, string>("CAS.Enabled", "true"), new KeyValuePair<string, string>("Sharpness.Sharpness", "0.25") }.ToList(),
        };
        store.SetImageReceipt("1245620", receipt);

        var reopened = new UpscalerStateStore(StatePath);

        var stored = reopened.Install("1245620")!.Install;
        Assert.Equal(install.Edited, stored.Edited);
        Assert.Equal(install.ImageOverrides, stored.ImageOverrides);
        Assert.Equal(1700000123.25, stored.VerificationSince);
        var back = reopened.ImageReceipt("1245620")!;
        Assert.Equal(receipt.Target, back.Target);
        Assert.Equal(receipt.Original, back.Original);
        Assert.Equal(receipt.Applied, back.Applied);
        var text = File.ReadAllText(StatePath);
        foreach (var field in new[] { "\"edited\"", "\"image_overrides\"", "\"verification_since\"", "\"image_settings\"", "\"original\"", "\"applied\"" })
        {
            Assert.Contains(field, text);
        }

        reopened.SetImageReceipt("1245620", null);
        Assert.Null(new UpscalerStateStore(StatePath).ImageReceipt("1245620"));
    }

    [Fact]
    public void AnInstallWithoutSettingsWritesNoSettingsFields()
    {
        var store = new UpscalerStateStore(StatePath);
        store.SetInstall("1", Sample("fsr-3.1", _root), 1);

        var text = File.ReadAllText(StatePath);

        foreach (var field in new[] { "\"edited\"", "\"image_overrides\"", "\"verification_since\"", "\"image_settings\"" })
        {
            Assert.DoesNotContain(field, text);
        }
    }

    private static InstalledUpscaler Sample(string build, string target) => new()
    {
        Build = build,
        Archive = "optiscaler-0.9.4",
        Proxy = "dxgi.dll",
        Target = target,
        Exe = "Binaries/Win64/Game.exe",
        Options = new UpscalerChoice { Quality = "performance", Model = "int8" },
        Managed = new[] { "FrameGen.Enabled" },
        Components = new[] { new KeyValuePair<string, string>("optiscaler-0.9.4", "abc") },
    };

    private static void WriteManifest(string game, bool incomplete)
    {
        Directory.CreateDirectory(Path.Combine(game, GameManifest.Folder));
        File.WriteAllText(Path.Combine(game, GameManifest.Folder, GameManifest.FileName),
            "{\"files\": {}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": []" + (incomplete ? ", \"incomplete\": true" : "") + "}");
    }
}
