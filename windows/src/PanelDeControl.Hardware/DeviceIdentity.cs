namespace PanelDeControl.Hardware;

public sealed class DeviceIdentity
{
    private const string XboxAllyXProduct = "ROG Xbox Ally X";

    private DeviceIdentity(
        string manufacturer,
        string productName,
        string profileId,
        bool isInitialTarget)
    {
        Manufacturer = manufacturer;
        ProductName = productName;
        ProfileId = profileId;
        IsInitialTarget = isInitialTarget;
    }

    public string Manufacturer { get; }

    public string ProductName { get; }

    public string ProfileId { get; }

    public bool IsInitialTarget { get; }

    public static DeviceIdentity FromDmi(string? manufacturer, string? productName)
    {
        var normalizedManufacturer = Normalize(manufacturer, "Unknown manufacturer");
        var normalizedProduct = Normalize(productName, "Unknown device");
        var isAsus = normalizedManufacturer.Contains(
            "ASUSTeK",
            StringComparison.OrdinalIgnoreCase);
        var isXboxAllyX = normalizedProduct.Contains(
            XboxAllyXProduct,
            StringComparison.OrdinalIgnoreCase);
        var isInitialTarget = isAsus && isXboxAllyX;

        return new DeviceIdentity(
            normalizedManufacturer,
            normalizedProduct,
            isInitialTarget ? "rog_xbox_ally_x" : "unknown",
            isInitialTarget);
    }

    private static string Normalize(string? value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
    }
}
