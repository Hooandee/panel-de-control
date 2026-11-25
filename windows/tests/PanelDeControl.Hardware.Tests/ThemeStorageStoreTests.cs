using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ThemeStorageStoreTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), $"pdc-storage-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ReadsBackWhatWasWrittenAfterReopening()
    {
        Assert.Null(new ThemeStorageStore(root).Set("hooandee-duo", "pdc.hybrid.dock.v1", "{\"size\":3}"));

        var snapshot = new ThemeStorageStore(root).Snapshot();

        Assert.Equal("{\"size\":3}", snapshot.Themes["hooandee-duo"]["pdc.hybrid.dock.v1"]);
        Assert.Empty(snapshot.Unreadable);
        Assert.Empty(ThemeLibrary.Scan(root).Themes);
    }

    [Fact]
    public void KeepsThemesApart()
    {
        var store = new ThemeStorageStore(root);
        Assert.Null(store.Set("hooandee-duo", "layout", "duo"));
        Assert.Null(store.Set("hooandee-bubble", "layout", "bubble"));

        var snapshot = store.Snapshot();

        Assert.Equal("duo", snapshot.Themes["hooandee-duo"]["layout"]);
        Assert.Equal("bubble", snapshot.Themes["hooandee-bubble"]["layout"]);
    }

    [Theory]
    [InlineData("../duo", "layout", "invalid_theme")]
    [InlineData("Duo", "layout", "invalid_theme")]
    [InlineData("hooandee-duo", "a b", "invalid_key")]
    [InlineData("hooandee-duo", "../x", "invalid_key")]
    public void RejectsUnsafeIdentities(string catalogId, string key, string code)
    {
        Assert.Equal(code, new ThemeStorageStore(root).Set(catalogId, key, "value"));
    }

    [Fact]
    public void RejectsOversizedValuesAndKeepsThePreviousOne()
    {
        var store = new ThemeStorageStore(root);
        Assert.Null(store.Set("hooandee-duo", "groups", "kept"));

        Assert.Equal("too_large", store.Set("hooandee-duo", "groups", new string('x', ThemeStorageStore.MaximumValueBytes + 1)));
        Assert.Equal("kept", store.Snapshot().Themes["hooandee-duo"]["groups"]);
    }

    [Fact]
    public void ReportsAnUnreadableFileInsteadOfAnEmptyOne()
    {
        Directory.CreateDirectory(Path.Combine(root, ThemeStorageStore.FolderName));
        File.WriteAllText(Path.Combine(root, ThemeStorageStore.FolderName, "hooandee-duo.json"), "{broken");
        var store = new ThemeStorageStore(root);

        var snapshot = store.Snapshot();
        Assert.Equal(new[] { "hooandee-duo" }, snapshot.Unreadable);
        Assert.False(snapshot.Themes.ContainsKey("hooandee-duo"));

        Assert.Null(store.Set("hooandee-duo", "layout", "grid"));
        Assert.Equal("grid", store.Snapshot().Themes["hooandee-duo"]["layout"]);
        Assert.True(File.Exists(Path.Combine(root, ThemeStorageStore.FolderName, "hooandee-duo.json.corrupt")));
    }
}
