using PanelDeControl.Core.Upscalers;
using Xunit;
using static PanelDeControl.TestSupport.TestTree;

namespace PanelDeControl.Hardware.Tests;

public sealed partial class UpscalerServiceTests
{
    private sealed class SlowArchive : IUserArchive
    {
        public ManualResetEventSlim Extracting { get; } = new();

        public ManualResetEventSlim Release { get; } = new();

        public ArchiveListing List(string path, string? password) => new(new[] { new ArchiveEntry("mod.dll", 3) }, false);

        public void Extract(string path, IReadOnlyList<KeyValuePair<string, string>> wanted, string destination, string? password)
        {
            Extracting.Set();
            Release.Wait(TimeSpan.FromSeconds(30));
            foreach (var pair in wanted)
            {
                Write(destination, pair.Key, "the mod");
            }
        }
    }

    [Fact]
    public async Task ExtractingAModNeverHoldsTheSettingsLock()
    {
        AddGame("100", "Plain");
        AddGame("200", "Other");
        var archive = new SlowArchive();
        var service = Service(archive: archive);
        var path = Zip(Downloads, "slow.zip", ("mod.dll", "x"));

        var adding = Task.Run(() => Send(service, UpscalersRequest.AddMod("100", path, null, true)));
        Assert.True(archive.Extracting.Wait(TimeSpan.FromSeconds(10)));

        var other = await Task.Run(() => Send(service, UpscalersRequest.RemoveMod("200", true))).WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(UpscalersResponseStatus.Ok, other.Status);

        archive.Release.Set();
        var added = await adding.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(UpscalersResponseStatus.Ok, added.Status);
        Assert.Equal(1, added.Game!.Mod!.Count);
    }

    [Fact]
    public async Task AModThatWritesInsidePanelsMetaFolderIsAConflict()
    {
        AddGame("100", "Plain");

        var response = await Send(Service(), UpscalersRequest.AddMod("100", Zip(Downloads, "meta.zip", ("a.dll", "x"), (".pdc-upscaler/manifest.json", "y")), null, true));

        Assert.Equal("mod_conflict", response.ErrorCode);
        Assert.Empty(ModFolders());
    }
}
