using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace PanelDeControl.Core.Devices;

[DataContract]
public sealed class DeviceCatalog
{
    public const int SupportedSchemaVersion = 1;

    private DeviceProfile[] profiles = Array.Empty<DeviceProfile>();

    private DeviceCatalog()
    {
    }

    [DataMember(Name = "schema_version", IsRequired = true)]
    public int SchemaVersion { get; private set; }

    [DataMember(Name = "generic", IsRequired = true)]
    public DeviceProfile Generic { get; private set; } = null!;

    public IReadOnlyList<DeviceProfile> Profiles => profiles;

    [DataMember(Name = "profiles", IsRequired = true)]
    private DeviceProfile[] ProfilesWire
    {
        get => profiles;
        set => profiles = value ?? Array.Empty<DeviceProfile>();
    }

    public static DeviceCatalog Parse(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new ArgumentException("Catalog must not be empty.", nameof(json));
        }

        var serializer = new DataContractJsonSerializer(typeof(DeviceCatalog));
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(json));
        if (serializer.ReadObject(stream) is not DeviceCatalog catalog || catalog.Generic is null)
        {
            throw new InvalidDataException("Device catalog is malformed.");
        }

        if (catalog.SchemaVersion != SupportedSchemaVersion)
        {
            throw new InvalidDataException(
                $"Unsupported device catalog schema {catalog.SchemaVersion}.");
        }

        return catalog;
    }

    public DeviceProfile Match(string? productName, string? sysVendor, string? boardName)
    {
        foreach (var profile in profiles)
        {
            if (profile.DmiMatches.Count > 0)
            {
                if (profile.DmiMatches.Any(match => match.Matches(productName, sysVendor, boardName)))
                {
                    return profile;
                }

                continue;
            }

            var name = productName ?? string.Empty;
            if (profile.MatchNames.Any(needle =>
                    name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0))
            {
                return profile;
            }
        }

        return Generic;
    }
}

[DataContract]
public sealed class DeviceProfile
{
    private string[] matchNames = Array.Empty<string>();
    private DmiMatchRule[] dmiMatches = Array.Empty<DmiMatchRule>();

    private DeviceProfile()
    {
    }

    [DataMember(Name = "key", IsRequired = true)]
    public string Key { get; private set; } = string.Empty;

    [DataMember(Name = "display_name", IsRequired = true)]
    public string DisplayName { get; private set; } = string.Empty;

    [DataMember(Name = "vendor", IsRequired = true)]
    public string Vendor { get; private set; } = string.Empty;

    [DataMember(Name = "chip", IsRequired = true)]
    public string Chip { get; private set; } = string.Empty;

    [DataMember(Name = "experimental", IsRequired = true)]
    public bool Experimental { get; private set; }

    [DataMember(Name = "limits", IsRequired = true)]
    public DeviceLimits Limits { get; private set; } = null!;

    public bool IsGeneric => string.Equals(Key, "generic", StringComparison.Ordinal);

    public IReadOnlyList<string> MatchNames => matchNames;

    public IReadOnlyList<DmiMatchRule> DmiMatches => dmiMatches;

    [DataMember(Name = "match_names", IsRequired = true)]
    private string[] MatchNamesWire
    {
        get => matchNames;
        set => matchNames = value ?? Array.Empty<string>();
    }

    [DataMember(Name = "dmi_matches", IsRequired = true)]
    private DmiMatchRule[] DmiMatchesWire
    {
        get => dmiMatches;
        set => dmiMatches = value ?? Array.Empty<DmiMatchRule>();
    }
}

[DataContract]
public sealed class DmiMatchRule
{
    private string[] boardNames = Array.Empty<string>();

    private DmiMatchRule()
    {
    }

    [DataMember(Name = "product_name")]
    public string? ProductName { get; private set; }

    [DataMember(Name = "sys_vendor", IsRequired = true)]
    public string SysVendor { get; private set; } = string.Empty;

    public IReadOnlyList<string> BoardNames => boardNames;

    [DataMember(Name = "board_names", IsRequired = true)]
    private string[] BoardNamesWire
    {
        get => boardNames;
        set => boardNames = value ?? Array.Empty<string>();
    }

    public bool Matches(string? productName, string? sysVendor, string? boardName)
    {
        if (ProductName is not null && !SameIdentity(productName, ProductName))
        {
            return false;
        }

        if (!SameIdentity(sysVendor, SysVendor))
        {
            return false;
        }

        return boardNames.Length == 0 || boardNames.Any(board => SameIdentity(boardName, board));
    }

    private static bool SameIdentity(string? left, string? right)
    {
        return string.Equals(
            (left ?? string.Empty).Trim(),
            (right ?? string.Empty).Trim(),
            StringComparison.OrdinalIgnoreCase);
    }
}

[DataContract]
public sealed class DeviceLimits
{
    private int[] tdpPresets = Array.Empty<int>();

    private DeviceLimits()
    {
    }

    [DataMember(Name = "tdp_min", IsRequired = true)]
    public int TdpMin { get; private set; }

    [DataMember(Name = "tdp_default", IsRequired = true)]
    public int TdpDefault { get; private set; }

    [DataMember(Name = "tdp_max", IsRequired = true)]
    public int TdpMax { get; private set; }

    [DataMember(Name = "tdp_max_charger", IsRequired = true)]
    public int TdpMaxCharger { get; private set; }

    [DataMember(Name = "charger_only_extra", IsRequired = true)]
    public bool ChargerOnlyExtra { get; private set; }

    [DataMember(Name = "cooler_max")]
    public int? CoolerMax { get; private set; }

    [DataMember(Name = "experimental_tdp_max_ac")]
    public int? ExperimentalTdpMaxAc { get; private set; }

    public IReadOnlyList<int> TdpPresets => tdpPresets;

    [DataMember(Name = "tdp_presets", IsRequired = true)]
    private int[] TdpPresetsWire
    {
        get => tdpPresets;
        set => tdpPresets = value ?? Array.Empty<int>();
    }
}
