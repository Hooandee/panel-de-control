using PanelDeControl.Core.Devices;

namespace PanelDeControl.Hardware;

public sealed class DeviceIdentity
{
    private DeviceIdentity(
        string manufacturer,
        string productName,
        string boardName,
        DeviceProfile? profile)
    {
        Manufacturer = manufacturer;
        ProductName = productName;
        BoardName = boardName;
        Profile = profile;
    }

    public string Manufacturer { get; }

    public string ProductName { get; }

    public string BoardName { get; }

    public DeviceProfile? Profile { get; }

    public bool IsRecognized => Profile is not null;

    public string ProfileId => Profile?.Key ?? "unknown";

    public string DisplayName => Profile?.DisplayName ?? ProductName;

    public static DeviceIdentity Unrecognized()
    {
        return FromDmi(null, null, null, null);
    }

    public static DeviceIdentity FromDmi(
        DeviceCatalog? catalog,
        string? manufacturer,
        string? productName,
        string? boardName)
    {
        var normalizedManufacturer = Normalize(manufacturer, "Unknown manufacturer");
        var normalizedProduct = Normalize(productName, "Unknown device");
        var normalizedBoard = Normalize(boardName, string.Empty);
        var match = catalog?.Match(productName, manufacturer, boardName);

        return new DeviceIdentity(
            normalizedManufacturer,
            normalizedProduct,
            normalizedBoard,
            match is null || match.IsGeneric ? null : match);
    }

    private static string Normalize(string? value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
    }
}
