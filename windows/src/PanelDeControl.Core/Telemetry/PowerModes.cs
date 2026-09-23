namespace PanelDeControl.Core.Telemetry;

public enum PowerMode
{
    BestEfficiency = 0,
    Balanced = 1,
    BetterPerformance = 2,
    BestPerformance = 3,
}

public static class PowerModes
{
    // Windows power-mode overlay scheme GUIDs (PowerGetActualOverlayScheme / PowerGetEffectiveOverlayScheme).
    private static readonly Dictionary<Guid, PowerMode> Overlays = new()
    {
        [new Guid("961cc777-2547-4f9d-8174-7d86181b8a7a")] = PowerMode.BestEfficiency,
        [Guid.Empty] = PowerMode.Balanced,
        [new Guid("3af9b8d9-7c97-431d-ad78-34a8bfea439f")] = PowerMode.BetterPerformance,
        [new Guid("ded574b5-45a0-4f42-8737-46345c09c238")] = PowerMode.BestPerformance,
    };

    public static PowerMode? FromOverlay(Guid overlay)
    {
        return Overlays.TryGetValue(overlay, out var mode) ? mode : null;
    }
}
