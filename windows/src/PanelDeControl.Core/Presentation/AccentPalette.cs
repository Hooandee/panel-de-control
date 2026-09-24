namespace PanelDeControl.Core.Presentation;

public readonly struct AccentColor
{
    public AccentColor(string id, uint argb)
    {
        Id = id;
        Argb = argb;
    }

    public string Id { get; }

    public uint Argb { get; }

    public byte A => (byte)(Argb >> 24);

    public byte R => (byte)(Argb >> 16);

    public byte G => (byte)(Argb >> 8);

    public byte B => (byte)Argb;
}

public static partial class AccentPalette
{
    public static AccentColor Resolve(string? id)
    {
        foreach (var accent in All)
        {
            if (string.Equals(accent.Id, id, StringComparison.Ordinal))
            {
                return accent;
            }
        }

        return All.First(accent => accent.Id == DefaultId);
    }
}
