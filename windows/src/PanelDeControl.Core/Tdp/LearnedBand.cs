namespace PanelDeControl.Core.Tdp;

public sealed class LearnedBand
{
    public int? Floor { get; set; }

    public int? Ceiling { get; set; }

    public int? Seed { get; set; }

    public int? ObservedMinimum { get; set; }

    public int? ObservedMaximum { get; set; }

    public bool Enough { get; set; }

    public string Reason { get; set; } = string.Empty;
}
