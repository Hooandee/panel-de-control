using System.Text;
using PanelDeControl.Core.Steam;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>What only a Windows disk shows: names without case, '\' separators and the registry's Steam path.</summary>
public sealed class WindowsDetectionTests
{
    [Fact]
    public void SteamRootFromTheRegistryAndFromLibraryFoldersIsOneLibrary()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        fileSystem.AddFile(
            @"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf",
            Encoding.UTF8.GetBytes("\"libraryfolders\" { \"0\" { \"path\" \"C:\\\\Program Files (x86)\\\\Steam\" } \"1\" { \"path\" \"D:\\\\SteamLibrary\" } }"));
        fileSystem.AddDirectory(@"D:\SteamLibrary\steamapps");

        var libraries = SteamLibrary.LibraryPaths(fileSystem, new[] { "c:/program files (x86)/steam" });

        Assert.Equal(new[] { "c:/program files (x86)/steam", @"D:\SteamLibrary" }, libraries);
    }

    [Fact]
    public void GameInASecondDriveLibraryIsFound()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        fileSystem.AddFile(
            @"D:\SteamLibrary\steamapps\appmanifest_2050650.acf",
            Encoding.UTF8.GetBytes("\"AppState\" { \"appid\" \"2050650\" \"name\" \"Resident Evil 4\" \"installdir\" \"RESIDENT EVIL 4  BIOHAZARD RE4\" \"StateFlags\" \"4\" \"buildid\" \"14567890\" }"));
        fileSystem.AddDirectory(@"D:\SteamLibrary\steamapps\common\RESIDENT EVIL 4  BIOHAZARD RE4");

        var app = SteamLibrary.FindInstalled(fileSystem, new[] { @"D:\SteamLibrary" }, "2050650");

        Assert.NotNull(app);
        Assert.Equal("Resident Evil 4", app!.Name);
        Assert.Equal("14567890", app.BuildId);
        Assert.Null(app.UpdateState);
    }

    [Fact]
    public void ReEnginePakMatchesWithoutCase()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        fileSystem.AddFile(@"C:\Games\RE\re4.exe", Array.Empty<byte>());
        fileSystem.AddFile(@"C:\Games\RE\d3d12\d3d12core.dll", Array.Empty<byte>());
        fileSystem.AddFile(@"C:\Games\RE\RE_CHUNK_000.PAK", Array.Empty<byte>());

        Assert.Equal(new[] { "d3d12" }, GameFolder.GraphicsApis(fileSystem, @"C:\Games\RE\re4.exe"));
    }

    [Fact]
    public void UpperCaseLibrariesStillCount()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);
        fileSystem.AddFile(@"C:\Games\Old\GAME.EXE", "MZ"u8.ToArray());
        fileSystem.AddFile(@"C:\Games\Old\NVNGX_DLSS.DLL", "x"u8.ToArray());

        var analysis = GameFolder.Analyze(fileSystem, @"C:\Games\Old");

        Assert.Equal("GAME.EXE", analysis.Exe);
        Assert.Equal(@"C:\Games\Old", analysis.Target);
        Assert.Equal("NVNGX_DLSS.DLL", Assert.Single(analysis.Inputs).Value.Single());
    }

    [Fact]
    public void EntryPointAcrossAReadChunkIsFound()
    {
        var needle = Encoding.ASCII.GetBytes("xessD3D12CreateContext");
        var image = new byte[(1024 * 1024) + 64];
        Array.Copy(needle, 0, image, (1024 * 1024) - 7, needle.Length);
        var fileSystem = new InMemoryFileSystem();
        fileSystem.AddFile("/game.exe", image);

        Assert.Equal(new[] { "xess" }, GameFolder.EmbeddedUpscalers(fileSystem, "/game.exe"));
    }

    [Fact]
    public void OversizedVdfIsRefused()
    {
        var error = Assert.Throws<VdfFormatException>(() => ValveTextVdf.Parse(new byte[ValveTextVdf.MaxBytes + 1]));

        Assert.Equal(VdfFormatException.Oversized, error.Code);
    }

    [Fact]
    public void UnreadableManifestFolderIsSkipped()
    {
        var fileSystem = new InMemoryFileSystem(windows: true);

        Assert.Empty(SteamLibrary.LibraryPaths(fileSystem, new[] { @"C:\Missing\Steam" }));
        Assert.Null(SteamLibrary.FindInstalled(fileSystem, new[] { @"C:\Missing\Steam" }, "292030"));
    }
}
