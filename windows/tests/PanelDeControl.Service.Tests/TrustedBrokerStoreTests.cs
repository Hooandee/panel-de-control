using PanelDeControl.Hardware;
using PanelDeControl.Service;
using Xunit;

namespace PanelDeControl.Service.Tests;

public sealed class TrustedBrokerStoreTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "pdc-broker-" + Guid.NewGuid().ToString("N"));
    private readonly string broker;
    private readonly string record;

    public TrustedBrokerStoreTests()
    {
        broker = Path.Combine(root, "HardwareBroker");
        Directory.CreateDirectory(Path.Combine(broker, "runtimes"));
        File.WriteAllText(Path.Combine(broker, "PanelDeControl.Hardware.exe"), "apphost");
        File.WriteAllText(Path.Combine(broker, "PanelDeControl.Hardware.dll"), "companion");
        File.WriteAllText(Path.Combine(broker, "runtimes", "native.dll"), "native");
        record = Path.Combine(root, TrustedBrokerStore.FileName);
    }

    public void Dispose() => Directory.Delete(root, recursive: true);

    [Fact]
    public void TrustsTheCompanionTheInstallerRecorded()
    {
        TrustedBrokerStore.Record(record, broker, development: true);

        Assert.True(new TrustedBrokerStore(record).Matches(broker));
    }

    [Fact]
    public void TrustsNothingWithoutARecord()
    {
        Assert.False(new TrustedBrokerStore(record).Matches(broker));
    }

    [Fact]
    public void RejectsACompanionWhoseLibraryWasSwapped()
    {
        TrustedBrokerStore.Record(record, broker, development: true);
        var store = new TrustedBrokerStore(record);
        Assert.True(store.Matches(broker));

        File.WriteAllText(Path.Combine(broker, "PanelDeControl.Hardware.dll"), "impostor");

        Assert.False(store.Matches(broker));
    }

    [Fact]
    public void RejectsAnExtraFileNextToTheCompanion()
    {
        TrustedBrokerStore.Record(record, broker, development: true);

        File.WriteAllText(Path.Combine(broker, "version.dll"), "proxy");

        Assert.False(new TrustedBrokerStore(record).Matches(broker));
    }

    [Fact]
    public void RefusesToRecordAFolderOutsideThePackageStoreUnlessItIsDevelopment()
    {
        Assert.Throws<InvalidOperationException>(() => TrustedBrokerStore.Record(record, broker, development: false));
        Assert.False(File.Exists(record));
    }

    [Fact]
    public void RejectsAnIdenticalCopyInAnotherFolder()
    {
        TrustedBrokerStore.Record(record, broker, development: true);
        var copy = CopyBroker(Path.Combine(root, "impostor", "HardwareBroker"));

        Assert.False(new TrustedBrokerStore(record).Matches(copy));
    }

    [Fact]
    public void FingerprintDoesNotDependOnWhereTheFolderLives()
    {
        var copy = CopyBroker(Path.Combine(root, "elsewhere", "HardwareBroker"));

        Assert.Equal(BrokerFingerprint.Compute(broker), BrokerFingerprint.Compute(copy));
    }

    private string CopyBroker(string copy)
    {
        foreach (var file in Directory.GetFiles(broker, "*", SearchOption.AllDirectories))
        {
            var target = Path.Combine(copy, Path.GetRelativePath(broker, file));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target);
        }

        return copy;
    }
}
