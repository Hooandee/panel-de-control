using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using PanelDeControl.Core.Upscalers;
using PanelDeControl.Hardware.Upscalers;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class HelixSrTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-helixsr-" + Guid.NewGuid().ToString("N"));

    public HelixSrTests() => Directory.CreateDirectory(root);

    public void Dispose() => Directory.Delete(root, true);

    private HelixSr New(IHelixProcess? process = null) => new(Path.Combine(root, "upscalers"), "HelixSR-3.2.0", process ?? new FakeHelixBridge());

    private string Zip(string name, params string[] entries)
    {
        var path = Path.Combine(root, name);
        using var archive = ZipFile.Open(path, ZipArchiveMode.Create);
        foreach (var entry in entries)
        {
            using var writer = new StreamWriter(archive.CreateEntry(entry).Open(), new UTF8Encoding(false));
            writer.Write("content of " + entry);
        }

        return path;
    }

    private static void Put(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    [Fact]
    public void ThePhysicalFoldersAreUnderPanelsOwnRoot()
    {
        var helix = New();

        Assert.Equal(Path.Combine(root, "upscalers", "helixsr"), helix.ReleasesFolder);
        Assert.Equal(Path.Combine(root, "upscalers", "python"), helix.PythonFolder);
        Assert.False(helix.Ready);
        Assert.Null(helix.Digest);
    }

    [Fact]
    public void OnlyTheReleaseFolderIsUnpackedAsItIsAndMarkedComplete()
    {
        var helix = New();
        var archive = Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py", "HelixSR-3.2.0/LICENSE", "HelixSR-3.2.0/HLX-FSR4/x.dll", "README.md", "Another/y.txt");
        var digest = new string('a', 64);

        helix.UnpackRelease(archive, digest);

        var release = Path.Combine(helix.ReleasesFolder, "HelixSR-3.2.0");
        Assert.Equal("content of HelixSR-3.2.0/LICENSE", File.ReadAllText(Path.Combine(release, "LICENSE")));
        Assert.True(File.Exists(Path.Combine(release, "HLX-FSR4", "x.dll")));
        Assert.Equal(new[] { "HelixSR-3.2.0", "current" }, Directory.GetFileSystemEntries(helix.ReleasesFolder).Select(Path.GetFileName).OrderBy(name => name, StringComparer.Ordinal));
        Assert.True(helix.ReleaseReady);
        Assert.Equal((release, digest, "HelixSR-3.2.0"), (helix.Release, helix.Digest, helix.ReleaseName));
    }

    [Fact]
    public void ANewerReleaseTakesOverAndTheOldOneGoes()
    {
        var helix = New();
        helix.UnpackRelease(Zip("HelixSR-3.1.0.zip", "HelixSR-3.1.0/setup/helixsr_bridge.py"), new string('1', 64));

        helix.UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py"), new string('2', 64));

        Assert.Equal(new[] { "HelixSR-3.2.0" }, Directory.GetDirectories(helix.ReleasesFolder).Select(Path.GetFileName));
        Assert.Equal("HelixSR-3.2.0", helix.ReleaseName);
        Assert.Equal(new string('2', 64), helix.Digest);
    }

    [Fact]
    public void ReunpackingTheSameReleaseReplacesItWithoutLeavingStagingBehind()
    {
        var helix = New();
        var archive = Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py", "HelixSR-3.2.0/new.txt");
        helix.UnpackRelease(archive, new string('1', 64));
        Put(Path.Combine(helix.Release, "stale.txt"), "stale");

        helix.UnpackRelease(archive, new string('1', 64));

        Assert.False(File.Exists(Path.Combine(helix.Release, "stale.txt")));
        Assert.True(File.Exists(Path.Combine(helix.Release, "new.txt")));
        Assert.Empty(Directory.GetFileSystemEntries(helix.ReleasesFolder, ".*"));
    }

    [Theory]
    [InlineData("HelixSR-3.2.0/../escape.txt")]
    [InlineData("HelixSR-3.2.0/sub/../../escape.txt")]
    [InlineData("HelixSR-3.2.0//escape.txt")]
    [InlineData("HelixSR-3.2.0/..\\escape.txt")]
    public void AnEntryThatLeavesTheReleaseIsRefusedAndNothingIsKept(string entry)
    {
        var helix = New();
        var archive = Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py", entry);

        var error = Assert.Throws<UpscalerException>(() => helix.UnpackRelease(archive, new string('a', 64)));

        Assert.Equal("unsafe_archive", error.Code);
        Assert.Empty(Directory.GetFileSystemEntries(helix.ReleasesFolder));
        Assert.False(File.Exists(Path.Combine(root, "upscalers", "escape.txt")));
    }

    [Fact]
    public void AReleaseWithoutTheBridgeIsUnpackFailed()
    {
        var error = Assert.Throws<UpscalerException>(() => New().UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/LICENSE"), new string('a', 64)));

        Assert.Equal(("unpack_failed", "bridge missing"), (error.Code, error.Detail));
    }

    [Fact]
    public void ANotAZipIsUnpackFailed()
    {
        var path = Path.Combine(root, "HelixSR-3.2.0.zip");
        File.WriteAllText(path, "nope");

        var error = Assert.Throws<UpscalerException>(() => New().UnpackRelease(path, new string('a', 64)));

        Assert.Equal(("unpack_failed", "InvalidDataException"), (error.Code, error.Detail));
    }

    [Fact]
    public void PythonIsUnpackedAsItIsIntoItsOwnFolder()
    {
        var helix = New();
        var digest = new string('c', 64);

        helix.UnpackPython(Zip("python.zip", "python.exe", "python314.dll", "python314._pth", "Lib/x.py"), digest);

        Assert.True(helix.PythonReady);
        Assert.True(helix.PythonIs(digest));
        Assert.False(helix.PythonIs(new string('d', 64)));
        Assert.True(File.Exists(Path.Combine(helix.PythonFolder, "Lib", "x.py")));
        Assert.Equal("content of python.exe", File.ReadAllText(Path.Combine(helix.PythonFolder, "python.exe")));
    }

    [Fact]
    public void APythonArchiveWithoutPythonExeIsRefusedAndTheOldPythonStays()
    {
        var helix = New();
        helix.UnpackPython(Zip("python.zip", "python.exe"), new string('c', 64));

        var error = Assert.Throws<UpscalerException>(() => helix.UnpackPython(Zip("other.zip", "readme.txt"), new string('d', 64)));

        Assert.Equal(("unpack_failed", "python.exe missing"), (error.Code, error.Detail));
        Assert.True(helix.PythonIs(new string('c', 64)));
    }

    [Theory]
    [InlineData("../evil.dll")]
    [InlineData("a/../../evil.dll")]
    [InlineData("C:/evil.dll")]
    [InlineData("/evil.dll")]
    public void APythonEntryThatLeavesItsFolderIsRefused(string entry)
    {
        var helix = New();

        var error = Assert.Throws<UpscalerException>(() => helix.UnpackPython(Zip("python.zip", "python.exe", entry), new string('c', 64)));

        Assert.Equal("unsafe_archive", error.Code);
        Assert.False(Directory.Exists(helix.PythonFolder));
    }

    [Fact]
    public async Task TheBridgeNeedsBothPythonAndTheRelease()
    {
        var bridge = new FakeHelixBridge();
        var helix = New(bridge);
        helix.UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py"), new string('a', 64));

        var noPython = await Assert.ThrowsAsync<UpscalerException>(() => helix.InstallAsync(root, CancellationToken.None));
        helix.UnpackPython(Zip("python.zip", "python.exe"), new string('c', 64));
        Directory.Delete(helix.ReleasesFolder, true);
        var noRelease = await Assert.ThrowsAsync<UpscalerException>(() => helix.RemoveAsync(root, CancellationToken.None));

        Assert.Equal(("helixsr_missing", "helixsr_missing"), (noPython.Code, noRelease.Code));
        Assert.Empty(bridge.Calls);
    }

    [Fact]
    public async Task TheBridgeRunsWithPythonOnTheReleaseAndTheGameAsPlainArguments()
    {
        var bridge = new FakeHelixBridge { Answer = _ => FakeHelixBridge.Ok(root) };
        var helix = New(bridge);
        helix.UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py"), new string('a', 64));
        helix.UnpackPython(Zip("python.zip", "python.exe"), new string('c', 64));
        var game = Path.Combine(root, "My Games", "Game \"One\"");

        var answer = await helix.InstallAsync(game, CancellationToken.None);

        var call = Assert.Single(bridge.Calls);
        Assert.Equal(Path.Combine(helix.PythonFolder, "python.exe"), call.Executable);
        Assert.Equal(new[] { "-X", "utf8", Path.Combine(helix.Release, "setup", "helixsr_bridge.py"), helix.Release, "install", "--game", game, "--way", "fsr" }, call.Arguments);
        Assert.Equal((helix.Release, TimeSpan.FromSeconds(180)), (call.WorkingDirectory, call.Timeout));
        Assert.Equal(Path.Combine(root, "Binaries", "Win64"), answer.ExeFolder);
    }

    [Theory]
    [InlineData(typeof(TimeoutException))]
    [InlineData(typeof(IOException))]
    [InlineData(typeof(InvalidOperationException))]
    [InlineData(typeof(System.ComponentModel.Win32Exception))]
    public async Task AProcessThatCannotRunIsHelixFailedWithTheExceptionsName(Type kind)
    {
        var helix = New(new FakeHelixBridge { Failure = (Exception)Activator.CreateInstance(kind)! });
        helix.UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py"), new string('a', 64));
        helix.UnpackPython(Zip("python.zip", "python.exe"), new string('c', 64));

        var error = await Assert.ThrowsAsync<UpscalerException>(() => helix.RemoveAsync(root, CancellationToken.None));

        Assert.Equal(("helixsr_failed", kind.Name), (error.Code, error.Detail));
    }

    [Fact]
    public async Task AnAnswerThatIsNotJsonIsHelixFailedWithTheTailOfItsErrors()
    {
        var bridge = new FakeHelixBridge { Answer = _ => new HelixProcessResult(1, "Traceback...", new string('x', 300) + "ImportError: boom") };
        var helix = New(bridge);
        helix.UnpackRelease(Zip("HelixSR-3.2.0.zip", "HelixSR-3.2.0/setup/helixsr_bridge.py"), new string('a', 64));
        helix.UnpackPython(Zip("python.zip", "python.exe"), new string('c', 64));

        var error = await Assert.ThrowsAsync<UpscalerException>(() => helix.InstallAsync(root, CancellationToken.None));

        Assert.Equal("helixsr_failed", error.Code);
        Assert.Equal(200, error.Detail.Length);
        Assert.EndsWith("ImportError: boom", error.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void AMarkerIsWrittenBesideTheOtherPanelFilesAndNeverThroughALink()
    {
        var target = Path.Combine(root, "game");
        Directory.CreateDirectory(target);

        HelixSr.WriteMarker(target, "fsr", "HelixSR-3.2.0");
        HelixSr.WriteMarker(target, "fsr", "HelixSR-3.3.0");

        Assert.True(HelixSr.HasMarker(target));
        Assert.Contains("HelixSR-3.3.0", File.ReadAllText(Path.Combine(target, ".pdc-upscaler", "helixsr.json")));
        Assert.Empty(Directory.GetFiles(Path.Combine(target, ".pdc-upscaler"), "*.tmp"));

        var linked = Path.Combine(root, "linked");
        var outside = Directory.CreateDirectory(Path.Combine(root, "outside")).FullName;
        Directory.CreateDirectory(linked);
        if (!Junction(Path.Combine(linked, ".pdc-upscaler"), outside))
        {
            return;
        }

        try
        {
            var error = Assert.Throws<UpscalerException>(() => HelixSr.WriteMarker(linked, "fsr", "HelixSR-3.2.0"));
            Assert.Equal("unsafe_folder", error.Code);
            Assert.Empty(Directory.GetFiles(outside));
        }
        finally
        {
            Directory.Delete(Path.Combine(linked, ".pdc-upscaler"));
        }
    }

    private static bool Junction(string link, string target)
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

    [Fact]
    public async Task TheProcessRunnerReadsOutputAndErrorsWithoutAShellDeadlock()
    {
        var result = await new HelixProcess().RunAsync("cmd.exe", new[] { "/c", "echo out& echo err 1>&2" }, root, TimeSpan.FromSeconds(30), CancellationToken.None);

        Assert.Equal(0, result.ExitCode);
        Assert.Equal("out", result.StandardOutput.Trim());
        Assert.Equal("err", result.StandardError.Trim());
    }

    [Fact]
    public async Task AProcessThatOutlivesTheTimeoutIsKilledAndReportedAsTimedOut()
    {
        var clock = Stopwatch.StartNew();

        await Assert.ThrowsAsync<TimeoutException>(() =>
            new HelixProcess().RunAsync(Path.Combine(Environment.SystemDirectory, "ping.exe"), new[] { "-n", "60", "127.0.0.1" }, root, TimeSpan.FromMilliseconds(500), CancellationToken.None));

        Assert.True(clock.Elapsed < TimeSpan.FromSeconds(20), clock.Elapsed.ToString());
    }

    [Fact]
    public async Task ACancelledRunIsCancelledNotTimedOut()
    {
        using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(300));

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            new HelixProcess().RunAsync(Path.Combine(Environment.SystemDirectory, "ping.exe"), new[] { "-n", "60", "127.0.0.1" }, root, TimeSpan.FromMinutes(1), cancel.Token));
    }

    [Fact]
    public async Task AnExecutableThatDoesNotExistFailsToStart()
    {
        await Assert.ThrowsAnyAsync<System.ComponentModel.Win32Exception>(() =>
            new HelixProcess().RunAsync(Path.Combine(root, "missing.exe"), Array.Empty<string>(), root, TimeSpan.FromSeconds(5), CancellationToken.None));
    }
}
