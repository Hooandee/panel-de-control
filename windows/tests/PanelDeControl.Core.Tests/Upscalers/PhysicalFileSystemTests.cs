using System.Text;
using PanelDeControl.Core.FileSystem;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

public sealed class PhysicalFileSystemTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pdc-fs-" + Guid.NewGuid().ToString("N"));

    public PhysicalFileSystemTests()
    {
        Directory.CreateDirectory(Path.Combine(_root, "Game", "Binaries", "Win64"));
        File.WriteAllBytes(Path.Combine(_root, "Game", "Binaries", "Win64", "game.exe"), Encoding.ASCII.GetBytes("MZ not really"));
    }

    public void Dispose()
    {
        try
        {
            Directory.Delete(_root, true);
        }
        catch (IOException)
        {
        }
    }

    [Fact]
    public void ListsFoldersAndFilesWithForwardSlashPaths()
    {
        var disk = PhysicalFileSystem.Instance;
        var root = _root.Replace('\\', '/');
        var entries = disk.List(root + "/Game/Binaries/Win64");
        var exe = Assert.Single(entries);
        Assert.Equal("game.exe", exe.Name);
        Assert.False(exe.IsDirectory);
        Assert.True(disk.IsDirectory(root + "/Game"));
        Assert.True(disk.IsFile(root + "/Game/Binaries/Win64/game.exe"));
        Assert.Equal(13, disk.Length(root + "/Game/Binaries/Win64/game.exe"));
    }

    [Fact]
    public void MissingPathsAnswerEmptyInsteadOfThrowing()
    {
        var disk = PhysicalFileSystem.Instance;
        var missing = _root + "/nope";
        Assert.Empty(disk.List(missing));
        Assert.False(disk.Exists(missing));
        Assert.False(disk.IsSymbolicLink(missing));
        Assert.Null(disk.Length(missing));
        Assert.Null(disk.OpenRead(missing));
    }

    [Fact]
    public void ReadsAFileAnotherProcessKeepsOpenForWriting()
    {
        var path = Path.Combine(_root, "Game", "OptiScaler.log");
        using var writer = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.ReadWrite);
        writer.Write(new byte[] { 1, 2, 3 }, 0, 3);
        writer.Flush();
        using var reader = PhysicalFileSystem.Instance.OpenRead(path);
        Assert.NotNull(reader);
        Assert.Equal(3, reader!.Length);
    }

    [Fact]
    public void LinkedFolderIsListedAsAFolderAndALink()
    {
        var link = Path.Combine(_root, "Linked");
        try
        {
            Directory.CreateSymbolicLink(link, Path.Combine(_root, "Game"));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return;
        }
        var entry = PhysicalFileSystem.Instance.List(_root.Replace('\\', '/')).Single(item => item.Name == "Linked");
        Assert.True(entry.IsDirectory);
        Assert.True(entry.IsSymbolicLink);
        Assert.True(PhysicalFileSystem.Instance.IsSymbolicLink(link));
    }

    [Fact]
    public void GameAnalysisRunsOnTheRealDisk()
    {
        var analysis = GameFolder.Analyze(PhysicalFileSystem.Instance, _root.Replace('\\', '/') + "/Game");
        Assert.NotNull(analysis);
    }
}
