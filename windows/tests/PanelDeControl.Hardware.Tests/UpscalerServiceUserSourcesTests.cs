using System.IO.Compression;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private string Downloads => Path.Combine(root, "profile", "Downloads");

    private string Desktop => Path.Combine(root, "profile", "Desktop");

    private static string Zip(string folder, string name, params (string Entry, string Content)[] files)
    {
        Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, name);
        File.Delete(path);
        using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
        foreach (var file in files)
        {
            using var writer = new StreamWriter(archive.CreateEntry(file.Entry).Open());
            writer.Write(file.Content);
        }

        return path;
    }

    private static string ModZip(string folder, string name = "ERSS-FG 1.2.zip") => Zip(folder, name,
        ("ERSS-FG 1.2/mod.dll", "the mod"), ("ERSS-FG 1.2/data/x.bin", "data"), ("ERSS-FG 1.2/dxgi.dll", "the mod's own loader"));

    private static void MarkEncrypted(string zip)
    {
        var bytes = File.ReadAllBytes(zip);
        for (var index = 0; index + 8 < bytes.Length; index++)
        {
            if (BitConverter.ToUInt32(bytes, index) == 0x04034b50)
            {
                bytes[index + 6] |= 1;
            }
            else if (BitConverter.ToUInt32(bytes, index) == 0x02014b50)
            {
                bytes[index + 8] |= 1;
            }
        }

        File.WriteAllBytes(zip, bytes);
    }

    private string[] ModFolders() => Directory.Exists(Path.Combine(root, "state", "user-mods"))
        ? Directory.GetFileSystemEntries(Path.Combine(root, "state", "user-mods")).Select(Path.GetFileName).Cast<string>().OrderBy(name => name).ToArray()
        : Array.Empty<string>();

    [Fact]
    public async Task ModCandidatesAreTheNewestArchivesInDownloadsAndDesktopWithTheDownloadInProgress()
    {
        AddGame("100", "Plain");
        var old = ModZip(Downloads, "old mod.zip");
        File.SetLastWriteTimeUtc(old, DateTime.UtcNow.AddDays(-3));
        var newest = ModZip(Desktop, "desktop mod.zip");
        File.SetLastWriteTimeUtc(newest, DateTime.UtcNow.AddDays(-1));
        Write(Downloads, "other.7z", "seven");
        File.SetLastWriteTimeUtc(Path.Combine(Downloads, "other.7z"), DateTime.UtcNow.AddHours(-1));
        Write(Downloads, "notes.txt", "not an archive");
        Write(Downloads, "big.zip.crdownload", "partial");
        Write(Downloads, "stale.part", "old partial");
        File.SetLastWriteTimeUtc(Path.Combine(Downloads, "stale.part"), DateTime.UtcNow.AddMinutes(-30));
        Write(root, "elsewhere/outside.zip", "never listed");

        var response = await Send(Service(), UpscalersRequest.ModCandidates("100"));

        Assert.Equal(UpscalersResponseStatus.Ok, response.Status);
        Assert.Equal(Downloads, response.Candidates!.Folder);
        Assert.Equal(new[] { "other.7z", "desktop mod.zip", "old mod.zip" }, response.Candidates.Candidates.Select(item => item.Filename));
        Assert.Equal(new FileInfo(newest).Length, response.Candidates.Candidates[1].Size);
        Assert.Equal(("big.zip.crdownload", 7L), (response.Candidates.Downloading!.Filename, response.Candidates.Downloading.Size));
        Assert.Equal("experimental_required", (await Send(Service(), UpscalersRequest.AddMod("100", old, null, false))).ErrorCode);
    }

    [Fact]
    public async Task AModIsKeptAppliedByTheNextInstallAndTakenOutWithTheUpscaler()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var archive = ModZip(Downloads);
        var service = Service(prepare: PrepareCache);

        var added = await Send(service, UpscalersRequest.AddMod("100", archive, null, true));

        Assert.Equal(UpscalersResponseStatus.Ok, added.Status);
        var mod = added.Game!.Mod!;
        Assert.Equal(("ERSS-FG 1.2.zip", 3, false), (mod.Filename, mod.Count, mod.Applied));
        Assert.Equal(new[] { "data/x.bin", "dxgi.dll", "mod.dll" }, mod.Files);
        Assert.Equal(before, Snapshot(game));
        Assert.Equal(new[] { "100" }, ModFolders());

        await Send(service, UpscalersRequest.Install("100", "fsr-3.1", null, null, true));
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        var target = Target(game);
        Assert.Equal("the mod", File.ReadAllText(Path.Combine(target, "mod.dll")));
        Assert.Equal("data", File.ReadAllText(Path.Combine(target, "data", "x.bin")));
        Assert.Equal("the mod's own loader", File.ReadAllText(Path.Combine(target, "dxgi.dll")));
        var detail = (await Send(service, UpscalersRequest.Game("100"))).Game!;
        Assert.True(detail.Mod!.Applied);
        Assert.NotEqual("dxgi.dll", detail.Install!.Proxy);
        Assert.Contains("\"mod\"", File.ReadAllText(StatePath));
        Assert.Contains("mod.dll", File.ReadAllText(Path.Combine(target, ".pdc-upscaler", "manifest.json")));

        File.WriteAllText(Path.Combine(target, "data", "x.bin"), "rewritten by the mod while it ran");
        await Send(service, UpscalersRequest.Uninstall("100", true));
        await RunDeferredAsync();

        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.Equal(before, Snapshot(game));
        Assert.Equal(new[] { "100" }, ModFolders());
        Assert.False((await Send(service, UpscalersRequest.Game("100"))).Game!.Mod!.Applied);
    }

    [Fact]
    public async Task RemovingTheModLeavesItInTheGameUntilTheUpscalerIsInstalledAgain()
    {
        var game = AddGame("100", "Plain");
        var service = Service(prepare: PrepareCache);
        await Send(service, UpscalersRequest.AddMod("100", ModZip(Downloads), null, true));
        await Send(service, UpscalersRequest.Install("100", "fsr-3.1", null, null, true));
        await RunDeferredAsync();

        var removed = await Send(service, UpscalersRequest.RemoveMod("100", true));

        Assert.Equal(UpscalersResponseStatus.Ok, removed.Status);
        Assert.Equal(("ERSS-FG 1.2.zip", 0, true), (removed.Game!.Mod!.Filename, removed.Game.Mod.Count, removed.Game.Mod.Removed == true));
        Assert.Empty(ModFolders());
        Assert.True(File.Exists(Path.Combine(Target(game), "mod.dll")));

        await Send(service, UpscalersRequest.Install("100", "fsr-3.1", null, null, true));
        await RunDeferredAsync();

        Assert.False(File.Exists(Path.Combine(Target(game), "mod.dll")));
        Assert.Null((await Send(service, UpscalersRequest.Game("100"))).Game!.Mod);
        Assert.Equal("experimental_required", (await Send(service, UpscalersRequest.RemoveMod("100", false))).ErrorCode);
    }

    [Fact]
    public async Task AModAddedForAnotherFolderThanTheExeIsRefusedAtInstallAndTheGameStaysAsItWas()
    {
        var game = AddGame("100", "Plain");
        Write(game, "Other/Game2.exe", "exe");
        var before = Snapshot(game);
        var service = Service(prepare: PrepareCache);
        await Send(service, UpscalersRequest.AddMod("100", ModZip(Downloads), null, true));
        await Send(service, UpscalersRequest.SetExe("100", "Other/Game2.exe", true));

        await Send(service, UpscalersRequest.Install("100", "fsr-3.1", null, null, true));
        await RunDeferredAsync();

        Assert.Equal(("error", "mod_moved"), (service.Job!.State, service.Job.Error));
        Assert.Equal(before, Snapshot(game));
    }

    [Fact]
    public async Task ModsThatCannotBeUsedAreRefusedWithLinuxsCodesAndKeepNothing()
    {
        var game = AddGame("100", "Plain");
        var before = Snapshot(game);
        var service = Service();
        async Task<string?> Add(string path, string? password = null) => (await Send(service, UpscalersRequest.AddMod("100", path, password, true))).ErrorCode;

        Assert.Equal("mod_unreadable", await Add(Path.Combine(Downloads, "missing.zip")));
        Assert.Equal("mod_unreadable", await Add(Path.Combine(root, "elsewhere", "outside.zip")));
        Write(Downloads, "notes.txt", "x");
        Assert.Equal("mod_unreadable", await Add(Path.Combine(Downloads, "notes.txt")));
        Write(Downloads, "broken.zip", "not a zip at all");
        Assert.Equal("mod_unreadable", await Add(Path.Combine(Downloads, "broken.zip")));
        Assert.Equal("mod_unreadable", await Add(@"\\server\share\mod.zip"));
        Assert.Equal("mod_unreadable", await Add(@"relative-only.zip"));

        foreach (var member in new[] { "../evil.dll", "/abs.dll", "a/../../b.dll", "C:/windows/x.dll", "-T/x.dll", "bad:stream.dll", "trailing./x.dll", "con.dll" })
        {
            Assert.Equal("mod_unsafe_archive", await Add(Zip(Downloads, "unsafe.zip", (member, "x"), ("fine.dll", "y"))));
            File.Delete(Path.Combine(Downloads, "unsafe.zip"));
        }

        Assert.Equal("mod_empty", await Add(Zip(Downloads, "empty.zip")));
        Assert.Equal("mod_conflict", await Add(Zip(Downloads, "conflict.zip", ("OptiScaler.ini", "x"), ("a.dll", "y"))));
        Assert.Equal("mod_conflict", await Add(Zip(Downloads, "conflict2.zip", ("nvngx.dll", "x"))));
        Assert.Equal("mod_ambiguous_files", await Add(Zip(Downloads, "twice.zip", ("a/x.dll", "1"), ("A/X.dll", "2"))));
        Assert.Equal("mod_layout", await Add(Zip(Downloads, "reaches.zip", ("Binaries/Win64/a.dll", "1"), ("Content/b.dll", "2"))));
        Assert.Equal("mod_too_many_files", await Add(Zip(Downloads, "many.zip", Enumerable.Range(0, 401).Select(index => ($"f{index}.bin", "x")).ToArray())));

        var protectedArchive = ModZip(Downloads, "protected.zip");
        MarkEncrypted(protectedArchive);
        Assert.Equal("mod_password_unsupported", await Add(protectedArchive));
        Assert.Equal("mod_password_unsupported", await Add(protectedArchive, "secret"));

        Assert.Equal("not_installed", (await Send(service, UpscalersRequest.AddMod("999", ModZip(Downloads), null, true))).ErrorCode);
        Assert.Empty(ModFolders());
        Assert.Equal(before, Snapshot(game));
        Assert.Null((await Send(service, UpscalersRequest.Game("100"))).Game!.Mod);
    }

    [Fact]
    public async Task AModCannotChangeUnderARunningJob()
    {
        AddGame("100", "Plain");
        var service = Service(prepare: PrepareCache);
        await Send(service, UpscalersRequest.Install("100", "fsr-3.1", null, null, true));

        Assert.Equal("busy", (await Send(service, UpscalersRequest.AddMod("100", ModZip(Downloads), null, true))).ErrorCode);
        Assert.Equal("busy", (await Send(service, UpscalersRequest.RemoveMod("100", true))).ErrorCode);
        await RunDeferredAsync();
        Assert.Equal(UpscalersResponseStatus.Ok, (await Send(service, UpscalersRequest.AddMod("100", ModZip(Downloads), null, true))).Status);
    }

    [Fact]
    public async Task AModAddedWithTheNameOfAFreeGameOffersItsDownloadPage()
    {
        AddGame("1245620", "Elden");

        var detail = (await Send(Service(), UpscalersRequest.Game("1245620"))).Game!;

        Assert.StartsWith("https://www.patreon.com/", detail.ModDownload);
        Assert.Null((await Send(Service(), UpscalersRequest.Game("1245620"))).Game!.Mod);
    }

    private UpscalerData UserFileData()
    {
        var assembly = typeof(UpscalerData).Assembly;
        const string prefix = "PanelDeControl.Hardware.Upscalers.recipes/";
        var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        foreach (var name in assembly.GetManifestResourceNames().Where(name => name.StartsWith(prefix, StringComparison.Ordinal)))
        {
            using var stream = assembly.GetManifestResourceStream(name)!;
            using var memory = new MemoryStream();
            stream.CopyTo(memory);
            files[name.Substring(prefix.Length)] = memory.ToArray();
        }

        files["games/1462040.json"] = System.Text.Encoding.UTF8.GetBytes(
            System.Text.Encoding.UTF8.GetString(files["games/1462040.json"]).Replace("\"vc-redist-x64\"", "\"puredark-upscaler-base\""));
        return new UpscalerData(Data.Catalog, Data.GpuRules, RecipeCatalog.Load(files));
    }

    private string LumaGame()
    {
        var game = AddGame("1462040", "Remake");
        var recipes = UserFileData().Recipes!;
        var asset = recipes.Assets[recipes.Dependencies["luma-ff7"].Asset!];
        var unpacked = Path.Combine(root, "cache", asset.Sha256, "unpacked");
        Write(unpacked, ".complete", "x");
        foreach (var member in recipes.Dependencies["luma-ff7"].Files.Values)
        {
            Write(unpacked, member, member);
        }

        return game;
    }

    [Fact]
    public async Task UserFileCandidatesAreTheDownloadsThatCarryWhatTheRecipeNames()
    {
        var data = UserFileData();
        Zip(Downloads, "UpscalerBasePlugin-502-1-1-2-1700000000.zip", ("UpscalerBasePlugin/PDPerfPlugin.dll", "MZ plugin"), ("readme.txt", "x"));
        Zip(Downloads, "other.zip", ("other.dll", "x"));
        Write(Desktop, "PDPerfPlugin.dll", "MZ loose");
        Write(Downloads, "notes.txt", "x");
        Zip(Downloads, "unsafe.zip", ("../PDPerfPlugin.dll", "x"));
        File.SetLastWriteTimeUtc(Path.Combine(Downloads, "UpscalerBasePlugin-502-1-1-2-1700000000.zip"), DateTime.UtcNow.AddDays(-1));

        var response = await Send(Service(data: data), UpscalersRequest.UserFileCandidates("puredark-upscaler-base"));

        Assert.Equal(UpscalersResponseStatus.Ok, response.Status);
        Assert.Equal(Downloads, response.Candidates!.Folder);
        Assert.Equal(new[] { "PDPerfPlugin.dll", "UpscalerBasePlugin-502-1-1-2-1700000000.zip" }, response.Candidates.Candidates.Select(item => item.Filename));
        Assert.Equal(new string?[] { null, "1.1.2" }, response.Candidates.Candidates.Select(item => item.Version));
        Assert.Equal("unknown_dependency", (await Send(Service(data: data), UpscalersRequest.UserFileCandidates("luma-ff7"))).ErrorCode);
        Assert.Equal("unknown_dependency", (await Send(Service(data: data), UpscalersRequest.UserFileCandidates("nothing"))).ErrorCode);
    }

    [Fact]
    public async Task AUserFileForARecipeDependencyIsJudgedKeptInstalledAndTakenOutWithTheUpscaler()
    {
        var data = UserFileData();
        var game = LumaGame();
        var before = Snapshot(game);
        var service = Service(prepare: PrepareCache, data: data);
        var dependency = (await Send(service, UpscalersRequest.Game("1462040"))).Game!.Recipe!.Dependencies!.Single(item => item.Id == "puredark-upscaler-base");
        Assert.Equal(("user_file", "missing"), (dependency.State, dependency.UserState));

        var added = await Send(service, UpscalersRequest.AddUserFile("1462040", "puredark-upscaler-base",
            Zip(Downloads, "UpscalerBasePlugin-502-1-1-2-1700000000.zip", ("a/PDPerfPlugin.dll", "plugin the user downloaded")), true));

        Assert.Equal(UpscalersResponseStatus.Ok, added.Status);
        dependency = added.Game!.Recipe!.Dependencies!.Single(item => item.Id == "puredark-upscaler-base");
        Assert.Equal(("ready", "1.1.2", "UpscalerBasePlugin-502-1-1-2-1700000000.zip"), (dependency.UserState, dependency.Installed, dependency.Filename));
        Assert.Equal(before, Snapshot(game));
        Assert.True(File.Exists(Path.Combine(root, "state", "user-files", "puredark-upscaler-base", "files", "PDPerfPlugin.dll")));

        await Send(service, UpscalersRequest.Install("1462040", "fsr-3.1", null, null, true));
        await RunDeferredAsync();

        Assert.Equal((UpscalerJobStates.Done, null), (service.Job!.State, service.Job.Error));
        Assert.Equal("plugin the user downloaded", File.ReadAllText(Path.Combine(Target(game), "PDPerfPlugin.dll")));
        await Send(service, UpscalersRequest.Uninstall("1462040", true));
        await RunDeferredAsync();
        Assert.Equal(before, Snapshot(game));

        var removed = await Send(service, UpscalersRequest.RemoveUserFile("1462040", "puredark-upscaler-base", true));
        Assert.Equal("missing", removed.Game!.Recipe!.Dependencies!.Single(item => item.Id == "puredark-upscaler-base").UserState);
        Assert.False(Directory.Exists(Path.Combine(root, "state", "user-files", "puredark-upscaler-base")));
        await Send(service, UpscalersRequest.Install("1462040", "fsr-3.1", null, null, true));
        await RunDeferredAsync();
        Assert.Equal(UpscalerJobStates.Done, service.Job!.State);
        Assert.False(File.Exists(Path.Combine(Target(game), "PDPerfPlugin.dll")));
    }

    [Fact]
    public async Task AUserFileOfAnotherVersionOrTheWrongFileIsReportedAndRefusedLikeLinux()
    {
        var data = UserFileData();
        LumaGame();
        var service = Service(data: data);
        async Task<UpscalersResponse> Add(string path, string dependency = "puredark-upscaler-base", bool experimental = true) =>
            await Send(service, UpscalersRequest.AddUserFile("1462040", dependency, path, experimental));

        var avoid = await Add(Zip(Downloads, "UpscalerBasePlugin-502-1-2-0-17.zip", ("PDPerfPlugin.dll", "x")));
        Assert.Equal("avoid", avoid.Game!.Recipe!.Dependencies!.Single(item => item.Id == "puredark-upscaler-base").UserState);
        var older = await Add(Zip(Downloads, "UpscalerBasePlugin-502-1-1-0-17.zip", ("PDPerfPlugin.dll", "x")));
        Assert.Equal("other_version", older.Game!.Recipe!.Dependencies!.Single(item => item.Id == "puredark-upscaler-base").UserState);

        Assert.Equal("user_file_wrong", (await Add(Zip(Downloads, "wrong.zip", ("other.dll", "x")))).ErrorCode);
        Assert.Equal("user_file_wrong", (await Add(Zip(Downloads, "twice.zip", ("a/PDPerfPlugin.dll", "1"), ("b/PDPerfPlugin.dll", "2")))).ErrorCode);
        Write(Downloads, "other.dll", "x");
        Assert.Equal("user_file_wrong", (await Add(Path.Combine(Downloads, "other.dll"))).ErrorCode);
        Assert.Equal("user_file_unreadable", (await Add(Zip(Downloads, "unsafe.zip", ("../PDPerfPlugin.dll", "x")))).ErrorCode);
        Assert.Equal("user_file_unreadable", (await Add(Path.Combine(Downloads, "missing.zip"))).ErrorCode);
        Assert.Equal("user_file_unreadable", (await Add(Path.Combine(root, "elsewhere", "outside.zip"))).ErrorCode);
        Write(Downloads, "notes.txt", "x");
        Assert.Equal("user_file_unreadable", (await Add(Path.Combine(Downloads, "notes.txt"))).ErrorCode);
        Assert.Equal("unknown_dependency", (await Add(Zip(Downloads, "ok.zip", ("PDPerfPlugin.dll", "x")), "luma-ff7")).ErrorCode);
        Assert.Equal("experimental_required", (await Add(Path.Combine(Downloads, "ok.zip"), experimental: false)).ErrorCode);
        Assert.Equal("experimental_required", (await Send(service, UpscalersRequest.RemoveUserFile("1462040", "puredark-upscaler-base", false))).ErrorCode);
        Assert.Equal("not_installed", (await Send(service, UpscalersRequest.AddUserFile("999", "puredark-upscaler-base", Path.Combine(Downloads, "ok.zip"), true))).ErrorCode);
    }
}
