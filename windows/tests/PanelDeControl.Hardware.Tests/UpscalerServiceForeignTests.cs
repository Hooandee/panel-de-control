using PanelDeControl.Core.Upscalers;
using static PanelDeControl.TestSupport.TestTree;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private const string OptiScalerProxy = "MZ\u0000\u0000OptiScaler v0.9.4 proxy dll";

    private string ForeignGame(string appId = "100")
    {
        var game = AddGame(appId, "Plain" + appId);
        var target = Target(game);
        Write(target, "OptiScaler.ini", "[Upscalers]\r\nDx12Upscaler=auto\r\n");
        Write(target, "OptiScaler.log", "log");
        Write(target, "OptiScaler/plugins/a.dll", "plugin");
        Write(target, "dxgi.dll", OptiScalerProxy);
        Write(target, "version.dll", "a real system library");
        return game;
    }

    private string BackupFolder(string appId = "100") => Directory.GetDirectories(Path.Combine(root, "state", "foreign", appId)).Single();

    [Fact]
    public async Task AdoptMovesAnotherToolsOptiScalerAsideAndRestorePutsItBackByteForByte()
    {
        var game = ForeignGame();
        var target = Target(game);
        var before = Snapshot(target);
        var service = Service();
        Assert.Equal(UpscalerGameStates.Foreign, (await Send(service, UpscalersRequest.Game("100"))).Game!.Game.State);

        var adopted = await Send(service, UpscalersRequest.AdoptForeign("100", true));

        Assert.Equal(UpscalersResponseStatus.Ok, adopted.Status);
        Assert.Equal(new[] { "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "dxgi.dll" }, adopted.Moved);
        Assert.False(File.Exists(Path.Combine(target, "OptiScaler.ini")));
        Assert.False(Directory.Exists(Path.Combine(target, "OptiScaler")));
        Assert.False(File.Exists(Path.Combine(target, "dxgi.dll")));
        Assert.True(File.Exists(Path.Combine(target, "version.dll")));
        var backup = BackupFolder();
        Assert.True(File.Exists(Path.Combine(backup, "OptiScaler", "plugins", "a.dll")));
        Assert.True(File.Exists(Path.Combine(backup, ForeignBackup.FileName)));
        var detail = (await Send(service, UpscalersRequest.Game("100"))).Game!;
        Assert.Equal(UpscalerGameStates.None, detail.Game.State);
        Assert.Null(detail.Foreign);
        Assert.Equal(1000, detail.ForeignBackup!.At);
        Assert.Contains("\"foreign_backup\"", File.ReadAllText(StatePath));
        var stored = new UpscalerStateStore(StatePath).ForeignBackupOf("100")!;
        Assert.Equal(new[] { "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "dxgi.dll" }, stored.Items);

        var restored = await Send(service, UpscalersRequest.RestoreForeign("100", true));

        Assert.Equal(UpscalersResponseStatus.Ok, restored.Status);
        Assert.Equal(new[] { "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "dxgi.dll" }, restored.Restored);
        Assert.Null(restored.Kept);
        Assert.Equal(before, Snapshot(target));
        Assert.False(Directory.Exists(Path.Combine(root, "state", "foreign", "100")));
        Assert.Null(new UpscalerStateStore(StatePath).ForeignBackupOf("100"));
        Assert.Null((await Send(service, UpscalersRequest.Game("100"))).Game!.ForeignBackup);
        Assert.Equal(UpscalerGameStates.Foreign, (await Send(service, UpscalersRequest.Game("100"))).Game!.Game.State);
    }

    [Fact]
    public async Task AnItemWhoseNameIsTakenAgainStaysInTheBackupAndIsReportedAsKept()
    {
        var game = ForeignGame();
        var target = Target(game);
        var service = Service();
        await Send(service, UpscalersRequest.AdoptForeign("100", true));
        Write(target, "dxgi.dll", "the game's new proxy");

        var restored = await Send(service, UpscalersRequest.RestoreForeign("100", true));

        Assert.Equal(new[] { "OptiScaler.ini", "OptiScaler.log", "OptiScaler" }, restored.Restored);
        Assert.Equal(new[] { "dxgi.dll" }, restored.Kept);
        Assert.Equal("the game's new proxy", File.ReadAllText(Path.Combine(target, "dxgi.dll")));
        Assert.Equal(OptiScalerProxy, File.ReadAllText(Path.Combine(BackupFolder(), "dxgi.dll")));
        Assert.Equal(new[] { "dxgi.dll" }, new UpscalerStateStore(StatePath).ForeignBackupOf("100")!.Items);
        Assert.NotNull((await Send(service, UpscalersRequest.Game("100"))).Game!.ForeignBackup);

        File.Delete(Path.Combine(target, "dxgi.dll"));
        var finished = await Send(service, UpscalersRequest.RestoreForeign("100", true));
        Assert.Equal(new[] { "dxgi.dll" }, finished.Restored);
        Assert.Equal(OptiScalerProxy, File.ReadAllText(Path.Combine(target, "dxgi.dll")));
        Assert.Null(new UpscalerStateStore(StatePath).ForeignBackupOf("100"));
    }

    [Fact]
    public async Task AdoptAndRestoreRefuseWhatLinuxRefuses()
    {
        var game = ForeignGame();
        var target = Target(game);
        var plain = AddGame("200", "Clean");
        var service = Service();

        Assert.Equal("experimental_required", (await Send(service, UpscalersRequest.AdoptForeign("100", false))).ErrorCode);
        Assert.Equal("experimental_required", (await Send(service, UpscalersRequest.RestoreForeign("100", false))).ErrorCode);
        Assert.Equal("not_installed", (await Send(service, UpscalersRequest.AdoptForeign("999", true))).ErrorCode);
        Assert.Equal("no_foreign", (await Send(service, UpscalersRequest.AdoptForeign("200", true))).ErrorCode);
        Assert.Equal("no_foreign", (await Send(service, UpscalersRequest.RestoreForeign("100", true))).ErrorCode);

        running.Add(Path.Combine(target, "Game.exe"));
        Assert.Equal("running", (await Send(service, UpscalersRequest.AdoptForeign("100", true))).ErrorCode);
        running.Clear();
        Assert.True(File.Exists(Path.Combine(target, "OptiScaler.ini")));

        await Send(service, UpscalersRequest.AdoptForeign("100", true));
        running.Add(Path.Combine(target, "Game.exe"));
        Assert.Equal("running", (await Send(service, UpscalersRequest.RestoreForeign("100", true))).ErrorCode);
        running.Clear();
        Assert.False(File.Exists(Path.Combine(target, "OptiScaler.ini")));
        Assert.True(Directory.Exists(plain));
    }

    [Fact]
    public async Task APanelInstallAndHelixSrAreNotAdopted()
    {
        var game = ForeignGame();
        var target = Target(game);
        var patched = Service(store => store.SetInstall("100", Install("fsr-3.1", target), 10), prepare: () => WriteManifest(target));
        Assert.Equal("still_patched", (await Send(patched, UpscalersRequest.AdoptForeign("100", true))).ErrorCode);
        Assert.True(File.Exists(Path.Combine(target, "OptiScaler.ini")));

        var helix = AddGame("300", "Helix");
        Write(Target(helix), "OptiScaler.ini", "[HelixSR]");
        Write(Target(helix), "helixsr-install.json", "{\"files\": []}");
        Assert.Equal("foreign_helix", (await Send(Service(), UpscalersRequest.AdoptForeign("300", true))).ErrorCode);
        Assert.True(File.Exists(Path.Combine(Target(helix), "OptiScaler.ini")));
    }

    [Fact]
    public async Task TheBackupRecordIsRecoveredFromItsFolderWhenPanelsStateIsWiped()
    {
        var game = ForeignGame();
        var target = Target(game);
        var before = Snapshot(target);
        await Send(Service(), UpscalersRequest.AdoptForeign("100", true));
        File.Delete(StatePath);
        var service = Service();

        var detail = (await Send(service, UpscalersRequest.Game("100"))).Game!;

        Assert.Equal(1000, detail.ForeignBackup!.At);
        Assert.Equal(new[] { "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "dxgi.dll" }, new UpscalerStateStore(StatePath).ForeignBackupOf("100")!.Items);
        File.Delete(StatePath);
        var restored = await Send(Service(), UpscalersRequest.RestoreForeign("100", true));
        Assert.Equal(UpscalersResponseStatus.Ok, restored.Status);
        Assert.Equal(before, Snapshot(target));
        Assert.Null(new UpscalerStateStore(StatePath).ForeignBackupOf("100"));
    }

    [Fact]
    public async Task ABackupRecordForAnotherGameFolderIsNotAdopted()
    {
        var game = ForeignGame();
        await Send(Service(), UpscalersRequest.AdoptForeign("100", true));
        File.Delete(StatePath);
        var other = AddGame("200", "Other");
        var backup = BackupFolder();
        Directory.CreateDirectory(Path.Combine(root, "state", "foreign", "200"));
        Directory.Move(backup, Path.Combine(root, "state", "foreign", "200", Path.GetFileName(backup)));

        var detail = (await Send(Service(), UpscalersRequest.Game("200"))).Game!;

        Assert.Null(detail.ForeignBackup);
        Assert.Equal("no_foreign", (await Send(Service(), UpscalersRequest.RestoreForeign("200", true))).ErrorCode);
        Assert.True(Directory.Exists(other) && Directory.Exists(game));
    }

    [Fact]
    public async Task AnItemThatIsALinkRefusesTheWholeMove()
    {
        var game = ForeignGame();
        var target = Target(game);
        Directory.Delete(Path.Combine(target, "OptiScaler"), true);
        var outside = Path.Combine(root, "elsewhere");
        Write(outside, "keep.txt", "outside");
        var junction = Path.Combine(target, "OptiScaler");
        using var made = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("cmd.exe", $"/c mklink /J \"{junction}\" \"{outside}\"")
        {
            CreateNoWindow = true,
            UseShellExecute = false,
        })!;
        made.WaitForExit();
        if (made.ExitCode != 0)
        {
            return;
        }

        var response = await Send(Service(), UpscalersRequest.AdoptForeign("100", true));

        Assert.Equal("unsupported_layout", response.ErrorCode);
        Assert.True(File.Exists(Path.Combine(target, "OptiScaler.ini")));
        Assert.True(File.Exists(Path.Combine(outside, "keep.txt")));
        Assert.False(Directory.Exists(Path.Combine(root, "state", "foreign")));
        Directory.Delete(junction);
    }
}
