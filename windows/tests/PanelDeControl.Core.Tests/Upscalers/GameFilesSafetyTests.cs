using System.Diagnostics;
using System.Runtime.InteropServices;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class GameFilesSafetyTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-safety-" + Guid.NewGuid().ToString("N"));
    private readonly string _game;
    private readonly string _outside;
    private readonly string _sources;

    public GameFilesSafetyTests()
    {
        _game = Path.Combine(_root, "Game");
        _outside = Path.Combine(_root, "Outside");
        _sources = Path.Combine(_root, "Sources");
        Directory.CreateDirectory(_game);
        Directory.CreateDirectory(_outside);
        Directory.CreateDirectory(_sources);
    }

    [Fact]
    public void AJunctionBetweenTheGameAndTheFileIsRefusedAndNothingLeavesTheGame()
    {
        if (!Junction(Path.Combine(_game, "bin"), _outside))
        {
            return;
        }

        var error = Assert.Throws<UpscalerException>(() => GameFiles.Apply(_game, Sources(("bin/x.dll", "panel")), null));

        Assert.Equal("unsafe_folder", error.Code);
        Assert.Empty(Directory.GetFileSystemEntries(_outside));
        Assert.False(Directory.Exists(Path.Combine(_game, GameManifest.Folder)));
    }

    [Fact]
    public void RemovingNeverFollowsAJunctionInAManifestPath()
    {
        File.WriteAllText(Path.Combine(_outside, "x.dll"), "not panel's");
        if (!Junction(Path.Combine(_game, "bin"), _outside))
        {
            return;
        }
        var meta = Path.Combine(_game, GameManifest.Folder);
        Directory.CreateDirectory(meta);
        File.WriteAllText(Path.Combine(meta, GameManifest.FileName), "{\"files\": {\"bin/x.dll\": null}, \"backups\": [], \"dirs\": [], \"configuration\": {}, \"owned\": []}");

        Assert.Equal("unsafe_folder", Assert.Throws<UpscalerException>(() => GameFiles.Remove(_game)).Code);

        Assert.Equal("not panel's", File.ReadAllText(Path.Combine(_outside, "x.dll")));
    }

    [Fact]
    public void AFileThatWillNotComeOutStillLetsTheBackedUpOriginalsReturn()
    {
        File.WriteAllText(Path.Combine(_game, "dxgi.dll"), "game dxgi");
        GameFiles.Apply(_game, Sources(("b.dll", "panel b"), ("dxgi.dll", "panel dxgi")), null);

        IReadOnlyList<string> kept;
        using (new FileStream(Path.Combine(_game, "b.dll"), FileMode.Open, FileAccess.Read, FileShare.None))
        {
            kept = GameFiles.Remove(_game);
        }

        Assert.Equal(new[] { "b.dll" }, kept);
        Assert.Equal("game dxgi", File.ReadAllText(Path.Combine(_game, "dxgi.dll")));
        Assert.NotNull(GameFiles.ReadManifest(_game));
    }

    [Fact]
    public void AnyFailureWhilePlacingRollsTheGameBack()
    {
        File.WriteAllText(Path.Combine(_game, "dxgi.dll"), "game dxgi");
        var calls = 0;

        Assert.Throws<InvalidOperationException>(() => GameFiles.Apply(_game, Sources(("a.dll", "a"), ("dxgi.dll", "panel dxgi")), null, (source, destination) =>
        {
            if (++calls == 2)
            {
                throw new InvalidOperationException("boom");
            }
            File.Copy(source, destination, false);
        }));

        Assert.Equal("game dxgi", File.ReadAllText(Path.Combine(_game, "dxgi.dll")));
        Assert.False(File.Exists(Path.Combine(_game, "a.dll")));
        Assert.False(Directory.Exists(Path.Combine(_game, GameManifest.Folder)));
    }

    [Fact]
    public void ProtectedLibrariesAndBackupsAreClearedFromALeftoverInstall()
    {
        File.WriteAllText(Path.Combine(_game, "dxgi.dll"), "game dxgi");
        GameFiles.Apply(_game, Sources(("dxgi.dll", "panel dxgi")), null, protect: true);
        var meta = Path.Combine(_game, GameManifest.Folder);
        File.Delete(Path.Combine(meta, GameManifest.FileName));

        GameFiles.RecoverOrphan(_game, _ => false);

        Assert.Equal("game dxgi", File.ReadAllText(Path.Combine(_game, "dxgi.dll")));
        Assert.False(Directory.Exists(meta));
    }

    [Fact]
    public void ReadOnlyLeftoversDoNotKeepTheManifestFolderAlive()
    {
        GameFiles.Apply(_game, Sources(("dxgi.dll", "panel dxgi")), null, protect: true);
        var stale = Path.Combine(_game, GameManifest.Folder, "backup", "stale.dll");
        Directory.CreateDirectory(Path.GetDirectoryName(stale)!);
        File.WriteAllText(stale, "old");
        File.SetAttributes(stale, FileAttributes.ReadOnly);

        Assert.Empty(GameFiles.Remove(_game));

        Assert.False(Directory.Exists(Path.Combine(_game, GameManifest.Folder)));
        Assert.False(File.Exists(Path.Combine(_game, "dxgi.dll")));
    }

    [Fact]
    public void RemovingAReframeworkInstallTakesOutWhatItGeneratedAndKeepsTheGamesOwnFiles()
    {
        File.WriteAllText(Path.Combine(_game, "config.ini"), "game config");
        Directory.CreateDirectory(Path.Combine(_game, "reframework"));
        File.WriteAllText(Path.Combine(_game, "reframework", "mine.lua"), "user");
        GameFiles.Apply(_game, Sources(("dinput8.dll", "panel fw"), (ReframeworkConfig.FileName, "REFrameworkConfig_MenuOpen=false")), "[OptiScaler]");
        File.WriteAllText(Path.Combine(_game, "re2_framework_log.txt"), "log");
        File.WriteAllText(Path.Combine(_game, "reframework_crash.txt"), "crash");
        File.WriteAllText(Path.Combine(_game, "ref_ui.ini"), "ui");
        Directory.CreateDirectory(Path.Combine(_game, "_storage_", "inner"));
        File.WriteAllText(Path.Combine(_game, "_storage_", "inner", "x.bin"), "x");
        File.WriteAllText(Path.Combine(_game, "unrelated.txt"), "keep");

        Assert.Empty(GameFiles.Remove(_game));

        Assert.False(File.Exists(Path.Combine(_game, "re2_framework_log.txt")));
        Assert.False(File.Exists(Path.Combine(_game, "reframework_crash.txt")));
        Assert.False(File.Exists(Path.Combine(_game, "ref_ui.ini")));
        Assert.False(Directory.Exists(Path.Combine(_game, "_storage_")));
        Assert.False(File.Exists(Path.Combine(_game, "dinput8.dll")));
        Assert.Equal("game config", File.ReadAllText(Path.Combine(_game, "config.ini")));
        Assert.Equal("user", File.ReadAllText(Path.Combine(_game, "reframework", "mine.lua")));
        Assert.Equal("keep", File.ReadAllText(Path.Combine(_game, "unrelated.txt")));
    }

    [Theory]
    [InlineData("data/settings.json", false)]
    [InlineData("autorun/mine.lua", true)]
    [InlineData("plugins/extra.dll", true)]
    public void AReframeworkFolderCreatedSinceTheInstallGoesOnlyWithoutUserScriptsOrPlugins(string file, bool kept)
    {
        GameFiles.Apply(_game, Sources(("dinput8.dll", "panel fw"), (ReframeworkConfig.FileName, "REFrameworkConfig_MenuOpen=false")), "[OptiScaler]");
        var path = Path.Combine(_game, "reframework", file.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "x");

        Assert.Empty(GameFiles.Remove(_game));

        Assert.Equal(kept, File.Exists(path));
    }

    [Fact]
    public void AnInstallWithoutASnapshotLeavesTheRuntimeFilesAlone()
    {
        GameFiles.Apply(_game, Sources(("dinput8.dll", "panel fw"), (ReframeworkConfig.FileName, "REFrameworkConfig_MenuOpen=false")), "[OptiScaler]");
        var path = Path.Combine(_game, GameManifest.Folder, GameManifest.FileName);
        File.WriteAllText(path, System.Text.RegularExpressions.Regex.Replace(File.ReadAllText(path), @",\s*""preexisting"": \[\]", ""));
        File.WriteAllText(Path.Combine(_game, "config.ini"), "game config");

        GameFiles.Remove(_game);

        Assert.Equal("game config", File.ReadAllText(Path.Combine(_game, "config.ini")));
    }

    [Fact]
    public void TwoSpellingsOfOneFileAreOneManifestEntryOnWindows()
    {
        var manifest = new GameManifest();
        manifest.Set("Bin/A.dll", null);
        manifest.Set("bin/a.dll", "hash");

        var windows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
        Assert.Equal(windows ? 1 : 2, manifest.Files.Count);
        Assert.Equal(windows, manifest.Owns("BIN/A.DLL"));
    }

    public void Dispose()
    {
        foreach (var link in Directory.GetDirectories(_root, "*", SearchOption.AllDirectories)
                     .Where(path => (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0).ToList())
        {
            Directory.Delete(link);
        }
        foreach (var file in Directory.GetFiles(_root, "*", SearchOption.AllDirectories))
        {
            File.SetAttributes(file, FileAttributes.Normal);
        }
        Directory.Delete(_root, true);
    }

    private IReadOnlyList<KeyValuePair<string, string>> Sources(params (string Relative, string Text)[] files)
    {
        var result = new List<KeyValuePair<string, string>>();
        foreach (var (relative, text) in files)
        {
            var path = Path.Combine(_sources, Guid.NewGuid().ToString("N"));
            File.WriteAllText(path, text);
            result.Add(new KeyValuePair<string, string>(relative, path));
        }
        return result;
    }

    internal static bool Junction(string link, string target)
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo("cmd.exe", "/c mklink /J \"" + link + "\" \"" + target + "\"")
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            })!;
            process.StandardOutput.ReadToEnd();
            process.StandardError.ReadToEnd();
            process.WaitForExit();
            return process.ExitCode == 0 && Directory.Exists(link);
        }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException or IOException)
        {
            return false;
        }
    }
}
