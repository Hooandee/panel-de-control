using System.Collections.Generic;
using System.Linq;

namespace PanelDeControl.Core.Presentation;

/// <summary>
/// What the Windows widget offers while Windows support is in preview: only blocks with real readings or
/// actions are shown, sections with none are hidden, and everything outside the themes section is read only.
/// </summary>
public static class WindowsPreview
{
    public const string InteractiveSectionId = "themes";

    public static IReadOnlyList<BlockDefinition> VisibleBlocks(SectionDefinition section) =>
        section.Blocks.Where(block => block.State == BlockState.Available).ToArray();

    public static IReadOnlyList<SectionDefinition> VisibleSections(IEnumerable<SectionDefinition> sections) =>
        sections.Where(section => VisibleBlocks(section).Count > 0).ToArray();

    public static bool IsReadOnly(SectionDefinition section) => section.Id != InteractiveSectionId;
}
