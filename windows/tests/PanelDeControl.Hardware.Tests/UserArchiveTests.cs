using System.Text;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class UserArchiveTests : IDisposable
{
    private static readonly KeyValuePair<string, string>[] Wanted = { new("wanted.dll", "dir\\wanted.dll") };
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-archive-" + Guid.NewGuid().ToString("N"));

    public UserArchiveTests()
    {
        Directory.CreateDirectory(_root);
    }

    public void Dispose() => UserFileStore.DeleteQuietly(_root);

    private string Script(string name, string body)
    {
        var path = Path.Combine(_root, name);
        File.WriteAllText(path, "@echo off\r\n" + body, new UTF8Encoding(false));
        return path;
    }

    private string Archive(string name)
    {
        var path = Path.Combine(_root, name);
        File.WriteAllText(path, "not read: the tools are fakes");
        return path;
    }

    private string Destination(string name = "out") => Path.Combine(_root, name, "files");

    [Fact]
    public void APasswordWithAQuoteNeverReachesSevenZip()
    {
        var sevenZip = Script("7z.cmd", "echo ran > \"%~dp0ran.txt\"\r\nexit /b 0");
        var archive = new UserArchive(sevenZip, null);
        var path = Archive("mod.7z");

        Assert.Equal("password_invalid", Assert.Throws<UserSourceException>(() => archive.List(path, "pa\"ss")).Code);
        Assert.Equal("password_invalid", Assert.Throws<UserSourceException>(() => archive.Extract(path, Wanted, Destination(), "a\" -ob\"")).Code);
        Assert.False(File.Exists(Path.Combine(_root, "ran.txt")));
        Assert.DoesNotContain(Directory.GetFileSystemEntries(Path.GetDirectoryName(Destination())!), entry => entry.Contains(".unpack"));
    }

    [Fact]
    public void SevenZipExtractsOnlyTheWantedMembersThroughAListFileAndSpeaksUtf8()
    {
        var sevenZip = Script("7z.cmd", "echo %* >> \"%~dp0args.txt\"\r\nif not \"%~1\"==\"x\" exit /b 0\r\nset \"p=%~6\"\r\ntype \"%p:~3%\" > \"%~dp0list.txt\"\r\nexit /b 0");
        var archive = new UserArchive(sevenZip, null);
        var path = Archive("mod.7z");

        archive.List(path, null);
        Assert.Equal("unsafe_archive", Assert.Throws<UserSourceException>(() => archive.Extract(path, Wanted, Destination(), "secret")).Code);

        var lines = File.ReadAllLines(Path.Combine(_root, "args.txt"));
        Assert.Contains("-sccUTF-8", lines[0]);
        Assert.Contains("l -slt -ba", lines[0]);
        Assert.Contains("x -y -spd -sccUTF-8 -scsUTF-8 -i@", lines[1]);
        Assert.DoesNotContain("wanted.dll", lines[1]);
        Assert.Equal(new[] { "dir\\wanted.dll" }, File.ReadAllLines(Path.Combine(_root, "list.txt")));
        Assert.Empty(Directory.GetFiles(_root, "*.lst", SearchOption.AllDirectories));
    }

    [Fact]
    public void TarExtractsOnlyTheWantedMembersAsEscapedPatternsAfterDoubleDash()
    {
        var tar = Script("tar.cmd", "echo %* >> \"%~dp0targs.txt\"\r\nexit /b 0");
        var archive = new UserArchive(null, tar);
        var wanted = new[] { new KeyValuePair<string, string>("a.dll", "dir/a[1].dll") };

        Assert.Equal("unsafe_archive", Assert.Throws<UserSourceException>(() => archive.Extract(Archive("mod.rar"), wanted, Destination(), null)).Code);

        var line = File.ReadAllLines(Path.Combine(_root, "targs.txt")).Single();
        Assert.Contains("-xf", line);
        Assert.EndsWith(" -- dir/a\\[1\\].dll", line.TrimEnd());
    }

    [Fact]
    public void AnEncryptedArchiveWithOnlyWindowsTarAnswersPasswordUnsupportedTheFirstTime()
    {
        var tar = Script("tar.cmd", "if \"%~1\"==\"-tvf\" (\r\necho -rw-r--r-- 1 u g 4 Jan 1 12:00 dir/wanted.dll\r\nexit /b 0\r\n)\r\necho bsdtar: Encrypted file is unsupported 1>&2\r\nexit /b 1");
        var archive = new UserArchive(null, tar);
        var path = Archive("mod.7z");

        Assert.Equal("dir/wanted.dll", Assert.Single(archive.List(path, null).Entries).Name);
        Assert.Equal("password_unsupported", Assert.Throws<UserSourceException>(() => archive.Extract(path, Wanted, Destination(), null)).Code);
        Assert.Equal("password_unsupported", Assert.Throws<UserSourceException>(() => archive.Extract(path, Wanted, Destination("again"), "secret")).Code);

        var headerEncrypted = Script("tar2.cmd", "echo bsdtar: Passphrase required for this entry 1>&2\r\nexit /b 1");
        Assert.Equal("password_unsupported", Assert.Throws<UserSourceException>(() => new UserArchive(null, headerEncrypted).List(path, null)).Code);
    }

    [Fact]
    public void TarRefusesNamesItCouldNotReadBackInsteadOfCorruptingThem()
    {
        var tar = Script("tar.cmd", "echo -rw-r--r-- 1 u g 4 Jan 1 12:00 dir/ñ.dll\r\nexit /b 0");

        Assert.Equal("name_unsupported", Assert.Throws<UserSourceException>(() => new UserArchive(null, tar).List(Archive("mod.7z"), null)).Code);
    }

    [Fact]
    public void SevenZipIsOnlyFoundWhereItsInstallerPutsItNeverOnPath()
    {
        var installed = Path.Combine(_root, "Program Files", "7-Zip");
        Directory.CreateDirectory(installed);
        var onPath = Path.Combine(_root, "tools");
        Directory.CreateDirectory(onPath);
        File.WriteAllText(Path.Combine(onPath, "7z.exe"), "fake");
        var empty = Path.Combine(_root, "Nothing");
        Directory.CreateDirectory(empty);
        var oldPath = Environment.GetEnvironmentVariable("PATH");
        try
        {
            Environment.SetEnvironmentVariable("PATH", onPath + Path.PathSeparator + oldPath);

            Assert.Null(UserArchive.Locate(null, new[] { empty }, Array.Empty<string>()).SevenZip);

            File.WriteAllText(Path.Combine(installed, "7z.exe"), "fake");
            Assert.Equal(Path.Combine(installed, "7z.exe"), UserArchive.Locate(null, new[] { Path.Combine(_root, "Program Files") }, Array.Empty<string>()).SevenZip);
            Assert.Equal(Path.Combine(installed, "7z.exe"), UserArchive.Locate(null, new[] { empty }, new[] { "\"" + installed + "\\\"" }).SevenZip);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PATH", oldPath);
        }
    }
}
