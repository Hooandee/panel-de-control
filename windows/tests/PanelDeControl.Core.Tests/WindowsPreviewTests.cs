using System.Linq;
using PanelDeControl.Core.Presentation;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class WindowsPreviewTests
{
    [Fact]
    public void ShowsOnlySectionsWithRealBlocksAndOnlyThoseBlocks()
    {
        var visible = WindowsPreview.VisibleSections(SectionCatalog.All);

        Assert.Equal(new[] { "power", "system", "fans", "themes", "settings" }, visible.Select(section => section.Id));
        Assert.All(visible, section => Assert.All(WindowsPreview.VisibleBlocks(section), block => Assert.Equal(BlockState.Available, block.State)));
        Assert.DoesNotContain(WindowsPreview.VisibleBlocks(SectionCatalog.Find("power")), block => block.Id == "autoTdp");
    }

    [Fact]
    public void OnlyThemesCanBeChanged()
    {
        Assert.False(WindowsPreview.IsReadOnly(SectionCatalog.Find("themes")));
        Assert.All(
            SectionCatalog.All.Where(section => section.Id != "themes"),
            section => Assert.True(WindowsPreview.IsReadOnly(section)));
    }
}
