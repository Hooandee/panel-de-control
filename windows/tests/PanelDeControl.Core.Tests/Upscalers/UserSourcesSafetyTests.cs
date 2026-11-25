using System.Diagnostics;
using PanelDeControl.Core.Upscalers;
using Xunit;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class UserSourcesSafetyTests : IDisposable
{
    private const string Member = "a/PDPerfPlugin.dll";
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-usersrc-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        var link = Path.Combine(_root, "link");
        if (Directory.Exists(link))
        {
            Directory.Delete(link);
        }

        UserFileStore.DeleteQuietly(_root);
    }

    private sealed class FakeArchive : IUserArchive
    {
        public ArchiveListing Listing { get; set; } = new(Array.Empty<ArchiveEntry>(), false);

        public List<List<string>> Extractions { get; } = new();

        public ArchiveListing List(string path, string? password) => Listing;

        public void Extract(string path, IReadOnlyList<KeyValuePair<string, string>> wanted, string destination, string? password)
        {
            Extractions.Add(wanted.Select(pair => pair.Value).ToList());
            foreach (var pair in wanted)
            {
                Write(destination, pair.Key, "MZ extracted");
            }
        }
    }

    private static RecipeDependency Dependency()
    {
        var dependency = (RecipeDependency)Activator.CreateInstance(typeof(RecipeDependency), true)!;
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.Id))!.SetValue(dependency, "base-plugin");
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.Kind))!.SetValue(dependency, "user_files");
        typeof(RecipeDependency).GetProperty(nameof(RecipeDependency.Files))!.SetValue(dependency,
            new Dictionary<string, string>(StringComparer.Ordinal) { ["PDPerfPlugin.dll"] = "PDPerfPlugin.dll" });
        return dependency;
    }

    private string Archive()
    {
        var path = Path.Combine(_root, "pack.zip");
        Write(_root, "pack.zip", "not read: the archive is a fake");
        return path;
    }

    private static ArchiveListing Listing(params (string Name, long Size)[] entries) =>
        new(entries.Select(entry => new ArchiveEntry(entry.Name, entry.Size)).ToList(), false);

    [Fact]
    public void AnArchiveTooBigForTheModCapsIsRefusedBeforeAnythingIsExtractedForUserFilesToo()
    {
        var fake = new FakeArchive();
        var store = new UserFileStore(Path.Combine(_root, "store"), fake);
        var dependency = Dependency();
        var cases = new Dictionary<string, ArchiveListing>
        {
            ["too_many_files"] = new(Enumerable.Range(0, UserMods.MaximumFiles).Select(index => new ArchiveEntry($"f{index}.bin", 1))
                .Append(new ArchiveEntry(Member, 1)).ToList(), false),
            ["too_large"] = Listing((Member, 1), ("bomb.bin", UserFiles.MaximumMember + 1)),
        };
        cases["too_large (total)"] = new ArchiveListing(Enumerable.Range(0, 10).Select(index => new ArchiveEntry($"part{index}.bin", UserFiles.MaximumMember))
            .Append(new ArchiveEntry(Member, 1)).ToList(), false);

        foreach (var item in cases)
        {
            fake.Listing = item.Value;
            var expected = item.Key.Split(' ')[0];
            Assert.Equal(expected, store.Inspect(dependency, Archive()).Reason);
            Assert.Equal(expected, Assert.Throws<UserSourceException>(() => store.Adopt(dependency, Archive())).Code);
        }

        Assert.Empty(fake.Extractions);
        Assert.Equal("missing", store.Status(dependency).State);
    }

    [Fact]
    public void OnlyTheWantedMembersAreExtractedFromAUserFileArchive()
    {
        var fake = new FakeArchive { Listing = Listing(("readme.txt", 10), (Member, 10), ("a/big.bin", 200_000_000)) };
        var store = new UserFileStore(Path.Combine(_root, "store"), fake);
        var dependency = Dependency();

        var status = store.Adopt(dependency, Archive());

        Assert.Equal("ready", status.State);
        Assert.Equal(new[] { new[] { Member } }, fake.Extractions.Select(list => list.ToArray()));
    }

    [Fact]
    public void AFailedSecondMoveBringsTheOldCopyBackAndAStaleSetAsideCopyIsPutBackOnTheNextUse()
    {
        var store = new UserFileStore(Path.Combine(_root, "store"), new FakeArchive());
        var dependency = Dependency();
        Write(_root, "old/PDPerfPlugin.dll", "MZ old");
        Write(_root, "new/PDPerfPlugin.dll", "MZ new");
        store.Adopt(dependency, Path.Combine(_root, "old", "PDPerfPlugin.dll"));
        var stored = Path.Combine(store.Root, "base-plugin", "files", "PDPerfPlugin.dll");

        var prepared = store.Prepare(dependency, Path.Combine(_root, "new", "PDPerfPlugin.dll"));
        Directory.Delete(prepared.Staging, true);
        Assert.Equal("unreadable", Assert.Throws<UserSourceException>(() => store.Commit(prepared)).Code);

        Assert.Equal("MZ old", File.ReadAllText(stored));
        Assert.DoesNotContain(Directory.GetDirectories(store.Root), name => name.Contains(".old-"));

        var hex = Guid.NewGuid().ToString("N");
        Directory.Move(Path.Combine(store.Root, "base-plugin"), Path.Combine(store.Root, "base-plugin.old-" + hex));
        var stale = Path.Combine(store.Root, ".base-plugin-" + Guid.NewGuid().ToString("N"));
        var fresh = Path.Combine(store.Root, ".base-plugin-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stale);
        Directory.CreateDirectory(fresh);
        Directory.SetCreationTimeUtc(stale, DateTime.UtcNow.AddHours(-5));
        Directory.SetLastWriteTimeUtc(stale, DateTime.UtcNow.AddHours(-5));

        var again = store.Prepare(dependency, Path.Combine(_root, "new", "PDPerfPlugin.dll"));
        store.Discard(again);

        Assert.Equal("MZ old", File.ReadAllText(stored));
        Assert.False(Directory.Exists(stale));
        Assert.True(Directory.Exists(fresh));
        Assert.DoesNotContain(Directory.GetDirectories(store.Root), name => name.Contains(".old-"));
    }

    [Fact]
    public void AModCannotWriteInsidePanelsMetaFolder()
    {
        foreach (var members in new[]
        {
            new[] { "a.dll", ".pdc-upscaler/manifest.json" },
            new[] { "a.dll", ".PDC-Upscaler/x/y.bin" },
            new[] { "wrap/a.dll", "wrap/.pdc-upscaler/manifest.json" },
        })
        {
            Assert.Equal("conflict", Assert.Throws<UserSourceException>(() => UserMods.Layout(members, "")).Code);
        }

        Assert.Equal("conflict", Assert.Throws<UserSourceException>(() => UserMods.Layout(new[] { "Bin/Win64/a.dll", "Bin/Win64/.pdc-upscaler/m.json" }, "Bin/Win64", new[] { "Bin" })).Code);
        Assert.Equal(2, UserMods.Layout(new[] { "x/a.dll", "y/sub/.pdc-upscaler/q" }, "").Count);
    }

    [Theory]
    [InlineData("CONIN$", true)]
    [InlineData("dir/conout$.dll", true)]
    [InlineData("COM\u00B9.txt", true)]
    [InlineData("a/LPT\u00B3", true)]
    [InlineData("COM\u00B2.dll", true)]
    [InlineData("CON .txt", true)]
    [InlineData("nul  .x", true)]
    [InlineData("con.txt", true)]
    [InlineData("COM1", true)]
    [InlineData("COM0.dll", false)]
    [InlineData("COM10", false)]
    [InlineData("console.dll", false)]
    [InlineData("conin.dll", false)]
    [InlineData("a/b.dll", false)]
    public void NamesWindowsWouldNotCreateAsTheArchiveMeansAreRefused(string member, bool invalid) =>
        Assert.Equal(invalid, UserMods.InvalidOnWindows(member));

    [Fact]
    public void OnlyRealLinksCountAsLinksAndCandidatesAgreeWithWhatCanBeChosen()
    {
        Write(_root, "real/mod.zip", "x");
        var link = Path.Combine(_root, "link");
        using (var process = Process.Start(new ProcessStartInfo("cmd.exe", $"/c mklink /J \"{link}\" \"{Path.Combine(_root, "real")}\"") { CreateNoWindow = true, UseShellExecute = false })!)
        {
            process.WaitForExit();
            Assert.Equal(0, process.ExitCode);
        }

        Assert.False(UserFiles.IsLink(Path.Combine(_root, "real", "mod.zip")));
        Assert.False(UserFiles.IsLink(Path.Combine(_root, "real")));
        Assert.True(UserFiles.IsLink(link));
        Assert.True(UserFiles.NotPlain(Path.Combine(link, "mod.zip")));
        Assert.False(UserFiles.NotPlain(Path.Combine(_root, "real", "mod.zip")));
        Assert.Single(UserMods.Candidates(new[] { Path.Combine(_root, "real") }));
        Assert.Empty(UserMods.Candidates(new[] { link }));
    }

    [Fact]
    public void AMappedNetworkDriveIsNotAPlainPath()
    {
        var path = Path.Combine(_root, "mod.zip");

        Assert.True(UserFiles.NotPlain(path, _ => DriveType.Network));
        Assert.False(UserFiles.NotPlain(path, _ => DriveType.Fixed));
        Assert.True(UserFiles.NotPlain(@"\\server\share\mod.zip", _ => DriveType.Fixed));
    }
}
