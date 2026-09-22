using PanelDeControl.Core.Devices;

namespace PanelDeControl.Hardware;

public static class DeviceCatalogResource
{
    public const string ResourceName = "PanelDeControl.Hardware.Devices.catalog.json";

    public static DeviceCatalog? TryLoad()
    {
        try
        {
            using var stream = typeof(DeviceCatalogResource).Assembly
                .GetManifestResourceStream(ResourceName);
            if (stream is null)
            {
                return null;
            }

            using var reader = new StreamReader(stream);
            return DeviceCatalog.Parse(reader.ReadToEnd());
        }
        catch
        {
            return null;
        }
    }
}
