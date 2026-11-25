using System.Collections.Generic;
using System.Linq;

namespace PanelDeControl.Core.Presentation;

/// <summary>
/// What the Windows widget offers while Windows support is in preview: only blocks with real readings or
/// actions are shown, sections with none are hidden, and everything outside the interactive sections is read only
/// except blocks that change nothing on the machine: showing diagnostics and sending a report.
/// </summary>
public static class WindowsPreview
{
    // Upscalers only write to game folders the user owns and only after its own experimental switch.
    private static readonly HashSet<string> InteractiveSections = new() { "themes", "upscalers" };

    private static readonly HashSet<string> MachineNeutralBlocks = new() { "settings.diagnostics", "settings.reports" };

    public static IReadOnlyList<BlockDefinition> VisibleBlocks(SectionDefinition section) =>
        section.Blocks.Where(block => block.State == BlockState.Available).ToArray();

    public static IReadOnlyList<SectionDefinition> VisibleSections(IEnumerable<SectionDefinition> sections) =>
        sections.Where(section => VisibleBlocks(section).Count > 0).ToArray();

    public static bool IsReadOnly(SectionDefinition section, BlockDefinition block) =>
        !InteractiveSections.Contains(section.Id) && !MachineNeutralBlocks.Contains(section.Id + "." + block.Id);
}
