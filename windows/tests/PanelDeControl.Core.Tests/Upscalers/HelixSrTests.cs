using System.Text;
using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>
/// HelixSR's log, bridge answer, release unpacking rules and by-hand restore must give the Linux backend's answers;
/// the log verdicts come from tests/test_upscalers_helix_log_parity.py.
/// </summary>
public sealed class HelixSrTests : IDisposable
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "helix_logs.json")))!.AsObject();
    private readonly string _folder = Path.Combine(Path.GetTempPath(), "pdc-helix-" + Guid.NewGuid().ToString("N"));

    public HelixSrTests() => Directory.CreateDirectory(_folder);

    public void Dispose() => Directory.Delete(_folder, true);

    public static IEnumerable<object[]> ReadCases() => Names("read");

    public static IEnumerable<object[]> InstallCases() => Names("install");

    [Theory]
    [MemberData(nameof(ReadCases))]
    public void ReadsLogsLikeTheLinuxBackend(string name)
    {
        var fixture = Case("read", name);
        Write(fixture["files"]!.AsObject());
        DateTime? since = fixture["since"] is JsonValue seconds ? Utc(seconds.GetValue<long>()) : null;
        var logs = fixture["logs"]!.AsArray().Select(item => Path.Combine(_folder, item!.GetValue<string>().Replace('/', Path.DirectorySeparatorChar)));

        var facts = HelixLog.Read(logs, since);

        AssertFacts(fixture["expected"]!.AsObject(), facts);
    }

    [Theory]
    [MemberData(nameof(InstallCases))]
    public void ReadsAnInstallLikeTheLinuxBackend(string name)
    {
        var fixture = Case("install", name);
        Write(fixture["files"]!.AsObject());
        var recorded = fixture["install"]!.AsObject();
        var install = new InstalledUpscaler
        {
            Engine = recorded["engine"]!.GetValue<string>(),
            Target = _folder,
            Log = recorded["log"] is JsonValue log ? Path.Combine(_folder, log.GetValue<string>().Replace('/', Path.DirectorySeparatorChar)) : "",
            HelixFile = recorded["helix_file"] is JsonValue file ? Path.Combine(_folder, file.GetValue<string>().Replace('/', Path.DirectorySeparatorChar)) : "",
        };
        var installedAt = recorded["installed_at"] is JsonValue at ? at.GetValue<double>() : 0;

        var facts = HelixLog.ReadInstall(install, installedAt);

        AssertFacts(fixture["expected"]!.AsObject(), facts);
    }

    [Fact]
    public void TheVerdictOfAnInstallReachesTheGamePage()
    {
        Write(Case("install", "storage-runtime-fresh")["files"]!.AsObject());
        var install = new InstalledUpscaler
        {
            Engine = "helixsr",
            Target = _folder,
            Log = Path.Combine(_folder, "bin", "helixsr.log"),
            HelixFile = Path.Combine(_folder, "bin", "helixsr-install.json"),
        };

        var verdict = UpscalerVerdict.Read(install, Fixture["mtime"]!.GetValue<long>());

        Assert.Equal(("active", "HLX FSR 4", null), (verdict!.Verdict, verdict.Observed, verdict.Provider));
    }

    [Fact]
    public void AnswerIsTheLastLineThatStartsWithABrace()
    {
        var game = HelixBridge.ParseAnswer(
            "progress\r\n{\"ok\": false, \"error\": \"old\"}\r\nnoise\r\n{\"ok\": true, \"game\": {\"exe_folder\": \"D:\\\\G\\\\bin\", \"log_path\": \"D:\\\\G\\\\bin\\\\helixsr.log\"}}\r\n",
            "ignored");

        Assert.Equal(("D:\\G\\bin", "D:\\G\\bin\\helixsr.log"), (game.ExeFolder, game.LogPath));
    }

    [Fact]
    public void AnAnswerWithoutAGameIsStillOk()
    {
        var game = HelixBridge.ParseAnswer("{\"ok\": true}", "");

        Assert.Equal((null, null), (game.ExeFolder, game.LogPath));
    }

    [Theory]
    [InlineData("{\"ok\": false, \"error\": \"HelixSR is not installed in D:\\\\G\"}", "", "HelixSR is not installed in D:\\G")]
    [InlineData("{\"ok\": 1}", "", "")]
    [InlineData("{\"error\": \"x\"}", "", "x")]
    [InlineData("not json", " Traceback: boom \n", "Traceback: boom")]
    [InlineData("{broken", "oops", "oops")]
    [InlineData("", "", "")]
    [InlineData("[1]", "", "")]
    public void AnythingButOkIsHelixFailedWithTheBridgesOwnWords(string output, string errors, string detail)
    {
        var error = Assert.Throws<UpscalerException>(() => HelixBridge.ParseAnswer(output, errors));

        Assert.Equal(("helixsr_failed", detail), (error.Code, error.Detail));
    }

    [Fact]
    public void TheBridgesWordsAreCutToTwoHundredCharacters()
    {
        var longText = new string('e', 500);

        Assert.Equal(200, Assert.Throws<UpscalerException>(() => HelixBridge.ParseAnswer("{\"ok\": false, \"error\": \"" + longText + "\"}", "")).Detail.Length);
        Assert.Equal(200, Assert.Throws<UpscalerException>(() => HelixBridge.ParseAnswer("nope", longText)).Detail.Length);
    }

    [Theory]
    [InlineData("HelixSR is not installed in D:\\Games\\X", true)]
    [InlineData("HelixSR Scaler is not installed in D:\\Games\\X", true)]
    [InlineData("Something HelixSR is not installed in", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void RecognizesTheBridgeSayingNothingIsInstalled(string? detail, bool expected) =>
        Assert.Equal(expected, HelixBridge.NotInstalled(detail));

    [Theory]
    [InlineData("HelixSR-3.2.0/setup/helixsr_bridge.py", "setup/helixsr_bridge.py")]
    [InlineData("HelixSR-3.2.0/LICENSE", "LICENSE")]
    [InlineData("HelixSR-3.2.0/HLX-FSR4/a/b.dll", "HLX-FSR4/a/b.dll")]
    [InlineData("HelixSR-3.2.0/setup/", null)]
    [InlineData("HelixSR-3.2.0/", null)]
    [InlineData("HelixSR-3.2.0", null)]
    [InlineData("HelixSR-3.2.1/setup/x.py", null)]
    [InlineData("Other/file", null)]
    [InlineData("README.md", null)]
    public void OnlyTheReleaseFolderIsUnpacked(string entry, string? expected) =>
        Assert.Equal(expected, HelixRelease.Destination(entry, "HelixSR-3.2.0"));

    [Theory]
    [InlineData("HelixSR-3.2.0/../evil.dll")]
    [InlineData("HelixSR-3.2.0/a/../../evil.dll")]
    [InlineData("HelixSR-3.2.0//evil.dll")]
    [InlineData("HelixSR-3.2.0/C:/evil.dll")]
    [InlineData("HelixSR-3.2.0/a\\..\\evil.dll")]
    [InlineData("HelixSR-3.2.0/./x")]
    public void AnEntryThatLeavesTheReleaseIsRefused(string entry) =>
        Assert.Equal("unsafe_archive", Assert.Throws<UpscalerException>(() => HelixRelease.Destination(entry, "HelixSR-3.2.0")).Code);

    [Theory]
    [InlineData("HelixSR-3.2.0.zip", "HelixSR-3.2.0")]
    [InlineData("HelixSR-3.10.12.zip", "HelixSR-3.10.12")]
    [InlineData("HelixSR-latest.zip", "HelixSR-3.2.0")]
    [InlineData("whatever.zip", "HelixSR-3.2.0")]
    [InlineData("HelixSR-3.2.0.1.zip", "HelixSR-3.2.0")]
    public void TheReleaseFolderIsNamedByTheArchive(string archive, string expected) =>
        Assert.Equal(expected, HelixRelease.NameOf(archive, "HelixSR-3.2.0"));

    [Fact]
    public void DigestsAreSha256Hex()
    {
        Assert.True(HelixRelease.IsDigest(new string('a', 64)));
        Assert.False(HelixRelease.IsDigest(new string('A', 64)));
        Assert.False(HelixRelease.IsDigest("HelixSR-3.2.0"));
        Assert.False(HelixRelease.IsDigest(null));
    }

    [Fact]
    public void RestoringByHandPutsTheGamesFileBack()
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "restore")).FullName;
        Put(folder, "amd_fidelityfx_dx12.dll", "HLX-FSR-4 drop-in");
        Put(folder, "amd_fidelityfx_dx12.original.dll", "game's own");
        Put(folder, "helixsr-install.json", "{\"files\": [\"amd_fidelityfx_dx12.dll\"]}");
        Put(folder, "helixsr.ini", "");

        Assert.True(HelixRestore.ByHand(folder));

        Assert.Equal("game's own", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.dll")));
        Assert.False(File.Exists(Path.Combine(folder, "amd_fidelityfx_dx12.original.dll")));
        Assert.False(File.Exists(Path.Combine(folder, "helixsr-install.json")));
        Assert.False(File.Exists(Path.Combine(folder, "helixsr.ini")));
    }

    [Fact]
    public void ARestoreNeverPutsAnOldBackupOverAGameUpdate()
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "updated")).FullName;
        Put(folder, "amd_fidelityfx_dx12.dll", "the update's new FSR");
        Put(folder, "amd_fidelityfx_dx12.original.dll", "old backup");
        Put(folder, "helixsr-install.json", "{\"files\": [\"amd_fidelityfx_dx12.dll\"]}");

        Assert.True(HelixRestore.ByHand(folder));

        Assert.Equal("the update's new FSR", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.dll")));
        Assert.Equal("old backup", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.original.dll")));
        Assert.False(File.Exists(Path.Combine(folder, "helixsr-install.json")));
    }

    [Fact]
    public void ABackupIdenticalToTheGamesFileGoes()
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "same")).FullName;
        Put(folder, "amd_fidelityfx_dx12.dll", "game's own");
        Put(folder, "amd_fidelityfx_dx12.original.dll", "game's own");
        Put(folder, "helixsr-install.json", "{\"files\": [\"amd_fidelityfx_dx12.dll\"]}");

        Assert.True(HelixRestore.ByHand(folder));

        Assert.False(File.Exists(Path.Combine(folder, "amd_fidelityfx_dx12.original.dll")));
        Assert.Equal("game's own", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.dll")));
    }

    [Fact]
    public void AHelixDllWithoutABackupOfAFidelityFxFileCannotBeUndone()
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "stuck")).FullName;
        Put(folder, "amd_fidelityfx_dx12.dll", "HelixSR build");
        Put(folder, "helixsr-install.json", "{\"files\": [\"amd_fidelityfx_dx12.dll\"]}");

        Assert.False(HelixRestore.ByHand(folder));

        Assert.True(File.Exists(Path.Combine(folder, "helixsr-install.json")));
        Assert.Equal("HelixSR build", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.dll")));
    }

    [Fact]
    public void AMissingDllComesBackFromItsBackup()
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "missing")).FullName;
        Put(folder, "amd_fidelityfx_dx12.original.dll", "game's own");
        Put(folder, "helixsr-install.json", "{\"files\": [\"amd_fidelityfx_dx12.dll\"]}");

        Assert.True(HelixRestore.ByHand(folder));

        Assert.Equal("game's own", File.ReadAllText(Path.Combine(folder, "amd_fidelityfx_dx12.dll")));
    }

    [Theory]
    [InlineData("{\"files\": [\"../x.dll\", \"sub/x.dll\", \"C:\\\\x.dll\", \"\", 5]}")]
    [InlineData("not json")]
    [InlineData("[1]")]
    public void OnlyPlainFileNamesOfTheRecordAreTouched(string record)
    {
        var folder = Directory.CreateDirectory(Path.Combine(_folder, "record")).FullName;
        Put(folder, "helixsr-install.json", record);
        Put(_folder, "x.dll", "outside");

        Assert.True(HelixRestore.ByHand(folder));

        Assert.Equal("outside", File.ReadAllText(Path.Combine(_folder, "x.dll")));
    }

    [Fact]
    public void AnInstallKeepsHelixSrsFieldsWithLinuxsNamesAndOtherEnginesStayAsTheyWere()
    {
        var path = Path.Combine(_folder, "state.json");
        var store = new UpscalerStateStore(path);
        store.SetInstall("1", new InstalledUpscaler
        {
            Build = "hlx-fsr4", Archive = "helixsr-3.2.0", Engine = "helixsr", Way = "fsr", Target = "D:/G/bin", ExeFolder = "D:/G/bin",
            Log = "D:/G/bin/helixsr.log", HelixFile = "D:/G/bin/helixsr-install.json",
        }, 5);
        store.SetInstall("2", new InstalledUpscaler { Build = "fsr-3.1", Proxy = "dxgi.dll", Target = "D:/H/bin" }, 6);

        var text = File.ReadAllText(path);
        var reloaded = new UpscalerStateStore(path);

        var helix = reloaded.Install("1")!.Install;
        Assert.Equal(("helixsr", "fsr", "D:/G/bin", "D:/G/bin/helixsr.log", "D:/G/bin/helixsr-install.json"), (helix.Engine, helix.Way, helix.ExeFolder, helix.Log, helix.HelixFile));
        Assert.Equal(1, text.Split("\"helix_file\"").Length - 1);
        Assert.Equal(1, text.Split("\"exe_folder\"").Length - 1);
        Assert.Equal(("", "", ""), (reloaded.Install("2")!.Install.Way, reloaded.Install("2")!.Install.ExeFolder, reloaded.Install("2")!.Install.Log));
    }

    private static void Put(string folder, string name, string text) => File.WriteAllText(Path.Combine(folder, name), text, new UTF8Encoding(false));

    private static DateTime Utc(long seconds) => DateTimeOffset.FromUnixTimeSeconds(seconds).UtcDateTime;

    private static IEnumerable<object[]> Names(string section) =>
        Fixture[section]!.AsArray().Select(item => new object[] { item!["name"]!.GetValue<string>() });

    private static JsonObject Case(string section, string name) =>
        Fixture[section]!.AsArray().Single(item => item!["name"]!.GetValue<string>() == name)!.AsObject();

    private void Write(JsonObject files)
    {
        foreach (var pair in files)
        {
            var item = pair.Value!.AsObject();
            var path = Path.Combine(_folder, pair.Key.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var bytes = new List<byte>();
            bytes.AddRange(Filler(item["lead"]!.GetValue<int>()));
            bytes.AddRange(new UTF8Encoding(false).GetBytes(item["text"]!.GetValue<string>()));
            bytes.AddRange(Filler(item["pad"]!.GetValue<int>()));
            File.WriteAllBytes(path, bytes.ToArray());
            File.SetLastWriteTimeUtc(path, Utc(item["mtime"]!.GetValue<long>()));
        }
    }

    private static byte[] Filler(int length)
    {
        var bytes = new byte[length];
        for (var index = 0; index < length; index++)
        {
            bytes[index] = index % 2 == 0 ? (byte)'x' : (byte)'\n';
        }

        return bytes;
    }

    private void AssertFacts(JsonObject expected, HelixLogFacts facts)
    {
        var recorded = expected["facts"]!.AsObject();
        Assert.Equal(recorded["present"]!.GetValue<bool>(), facts.Present);
        Assert.Equal(recorded["stale"]?.GetValue<bool>() ?? false, facts.Stale);
        Assert.Equal(recorded["upscaler"]?.GetValue<string>(), facts.Upscaler);
        Assert.Equal(recorded["output"] is JsonArray output ? output.Select(item => item!.GetValue<int>()).ToArray() : null, facts.Output);
        Assert.Equal(
            recorded["path"]?.GetValue<string>(),
            facts.Path is null ? null : Path.GetRelativePath(_folder, facts.Path).Replace('\\', '/'));
        Assert.Equal(expected["verdict"]!.GetValue<string>(), HelixLog.Verdict(facts));
    }
}
