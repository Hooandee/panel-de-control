using System.Collections.Generic;
using System.Linq;

namespace PanelDeControl.Core.Presentation;

public enum BlockState
{
    Available,
    Pending,
}

public sealed class BlockDefinition
{
    public BlockDefinition(string id, string resourceStem, string glyph, bool implementedOnWindows = false)
    {
        Id = id;
        ResourceStem = resourceStem;
        Glyph = glyph;
        ImplementedOnWindows = implementedOnWindows;
    }

    public string Id { get; }

    public string ResourceStem { get; }

    public string Glyph { get; }

    public bool ImplementedOnWindows { get; }

    public BlockState State => ImplementedOnWindows ? BlockState.Available : BlockState.Pending;
}

public sealed class SectionDefinition
{
    public SectionDefinition(string id, string resourceStem, uint accentArgb, string glyph, IReadOnlyList<BlockDefinition> blocks)
    {
        Id = id;
        ResourceStem = resourceStem;
        AccentArgb = accentArgb;
        Glyph = glyph;
        Blocks = blocks;
    }

    public string Id { get; }

    public string ResourceStem { get; }

    public uint AccentArgb { get; }

    public string Glyph { get; }

    public IReadOnlyList<BlockDefinition> Blocks { get; }
}

public static class SectionCatalog
{
    public static IReadOnlyList<SectionDefinition> All { get; } = new[]
    {
        new SectionDefinition("power", "Power", 0xFF287D8C, "", new[]
        {
            new BlockDefinition("tdp", "BlockTdp", "", implementedOnWindows: true),
            new BlockDefinition("energy", "BlockEnergy", "", implementedOnWindows: true),
            new BlockDefinition("steamPerformance", "BlockSteamPerformance", "", implementedOnWindows: true),
            new BlockDefinition("autoTdp", "BlockAutoTdp", ""),
        }),
        new SectionDefinition("system", "System", 0xFF647084, "", new[]
        {
            new BlockDefinition("eco", "BlockEco", ""),
            new BlockDefinition("battery", "BlockBattery", "", implementedOnWindows: true),
            new BlockDefinition("cpu", "BlockCpu", ""),
            new BlockDefinition("gpu", "BlockGpu", ""),
            new BlockDefinition("brightness", "BlockBrightness", "", implementedOnWindows: true),
            new BlockDefinition("volume", "BlockVolume", "", implementedOnWindows: true),
            new BlockDefinition("colores", "BlockRgb", ""),
        }),
        new SectionDefinition("display", "Display", 0xFFA05F79, "", new[]
        {
            new BlockDefinition("oled", "BlockOled", ""),
            new BlockDefinition("color", "BlockColor", ""),
            new BlockDefinition("hdr", "BlockHdr", ""),
            new BlockDefinition("night", "BlockNight", ""),
        }),
        new SectionDefinition("fans", "Fans", 0xFF39796E, "", new[]
        {
            new BlockDefinition("fanRpm", "BlockFanRpm", "", implementedOnWindows: true),
            new BlockDefinition("temps", "BlockTemps", "", implementedOnWindows: true),
            new BlockDefinition("curve", "BlockFanCurve", ""),
        }),
        new SectionDefinition("audio", "Audio", 0xFF96713E, "", new[]
        {
            new BlockDefinition("equalizer", "BlockEqualizer", ""),
        }),
        new SectionDefinition("mandos", "Controllers", 0xFF64609B, "", new[]
        {
            new BlockDefinition("manager", "BlockControllerManager", ""),
            new BlockDefinition("remap", "BlockRemap", ""),
            new BlockDefinition("settings", "BlockControllerSettings", ""),
            new BlockDefinition("magicModules", "BlockMagicModules", ""),
        }),
        new SectionDefinition("hud", "Hud", 0xFF3E7E5E, "", new[]
        {
            new BlockDefinition("overlay", "BlockHudOverlay", ""),
        }),
        new SectionDefinition("params", "Launch", 0xFF955E44, "", new[]
        {
            new BlockDefinition("launchOptions", "BlockLaunchOptions", ""),
        }),
        new SectionDefinition("cleaner", "Cleaner", 0xFF507E86, "", new[]
        {
            new BlockDefinition("steamCache", "BlockSteamCache", ""),
        }),
        new SectionDefinition("themes", "Themes", 0xFF925783, "", new[]
        {
            new BlockDefinition("accent", "BlockAccent", "", implementedOnWindows: true),
        }),
        new SectionDefinition("settings", "Settings", 0xFF626B73, "", new[]
        {
            new BlockDefinition("diagnostics", "BlockDiagnostics", "", implementedOnWindows: true),
            new BlockDefinition("reports", "BlockReports", ""),
            new BlockDefinition("updates", "BlockUpdates", ""),
        }),
    };

    public static SectionDefinition Find(string id) => All.First(section => section.Id == id);
}
