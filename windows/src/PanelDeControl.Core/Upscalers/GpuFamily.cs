using System.Text.RegularExpressions;
using PanelDeControl.Core.Data;

namespace PanelDeControl.Core.Upscalers;

/// <summary>A display GPU's PCI ids, as <c>0x</c>-prefixed lower-case hex.</summary>
public sealed class PciGpu
{
    public PciGpu(string vendor, string device)
    {
        Vendor = vendor.ToLowerInvariant();
        Device = device.ToLowerInvariant();
    }

    public string Vendor { get; }

    public string Device { get; }
}

public sealed class GpuFamilyResult
{
    public GpuFamilyResult(string generation, string source)
    {
        Generation = generation;
        Source = source;
    }

    /// <summary><c>rdna2</c>, <c>rdna3</c>, <c>rdna35</c>, <c>rdna4</c>, <c>intel</c> or <c>unknown</c>.</summary>
    public string Generation { get; }

    /// <summary><c>name</c>, <c>pci</c> or <c>unknown</c>.</summary>
    public string Source { get; }
}

/// <summary>
/// The GPU family upscaler suggestions follow, from <c>shared/upscalers/gpus.json</c> with the same rules as
/// <c>device_registry.gpu_facts</c>: the chip's name first, then the display GPUs' PCI ids in order.
/// </summary>
public sealed class GpuFamily
{
    private readonly Dictionary<string, string> _vendors;
    private readonly List<(string Generation, string[] Contains, Regex? Pattern)> _nameRules;
    private readonly Dictionary<string, string> _pciVendors;
    private readonly Dictionary<string, string> _amdPci;
    private readonly string _unknownAmd;

    private GpuFamily(Dictionary<string, string> vendors, List<(string, string[], Regex?)> nameRules, Dictionary<string, string> pciVendors,
        Dictionary<string, string> amdPci, string unknownAmd)
    {
        _vendors = vendors;
        _nameRules = nameRules;
        _pciVendors = pciVendors;
        _amdPci = amdPci;
        _unknownAmd = unknownAmd;
    }

    /// <summary>Rules that know no GPU, for when the file cannot be read: every family is <c>unknown</c>.</summary>
    public static GpuFamily None { get; } = new(new(), new(), new(), new(), "unknown");

    public static GpuFamily Parse(byte[] utf8)
    {
        var raw = BuildCatalog.Fields(DataValue.Parse(utf8),
            new[] { "schema_version", "vendors", "name_rules", "pci_vendors", "amd_pci", "unknown_amd" }, new[] { "notes" });
        if (!(raw.Get("schema_version") is DataNumber { Integer: { } version } && version == 1))
        {
            throw new DataFormatException("unsupported_schema");
        }
        var rules = new List<(string, string[], Regex?)>();
        foreach (var item in Array(raw.Get("name_rules")))
        {
            var rule = BuildCatalog.Fields(item, new[] { "generation" }, new[] { "contains", "pattern", "note" });
            var contains = rule.Get("contains") is { } list ? Array(list).Select(Text).ToArray() : System.Array.Empty<string>();
            var pattern = rule.Get("pattern") is { } text ? new Regex(Text(text), RegexOptions.CultureInvariant) : null;
            rules.Add((Text(rule.Get("generation")!), contains, pattern));
        }
        return new GpuFamily(Map(raw.Get("vendors")), rules, Map(raw.Get("pci_vendors")), Map(raw.Get("amd_pci")), Text(raw.Get("unknown_amd")!));
    }

    /// <summary>The vendor word the rules use, from Windows' <c>Win32_Processor.Manufacturer</c>.</summary>
    public static string CpuVendor(string? manufacturer) => (manufacturer ?? "").ToLowerInvariant() switch
    {
        "authenticamd" => "amd",
        "genuineintel" => "intel",
        var other => other,
    };

    /// <summary>PCI ids from a Windows PnP device id such as <c>PCI\VEN_1002&amp;DEV_150E&amp;SUBSYS_...</c>; null otherwise.</summary>
    public static PciGpu? FromPnpId(string? pnpDeviceId)
    {
        var match = Regex.Match(pnpDeviceId ?? "", @"^PCI\\VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})", RegexOptions.CultureInvariant);
        return match.Success ? new PciGpu("0x" + match.Groups[1].Value, "0x" + match.Groups[2].Value) : null;
    }

    public GpuFamilyResult Detect(string? vendor, string? chip, IReadOnlyList<PciGpu> displayGpus)
    {
        var byName = FromName(vendor, chip);
        if (byName != "unknown")
        {
            return new GpuFamilyResult(byName, "name");
        }
        var byPci = FromPci(displayGpus);
        return new GpuFamilyResult(byPci, byPci != "unknown" ? "pci" : "unknown");
    }

    private string FromName(string? vendor, string? chip)
    {
        if (_vendors.TryGetValue((vendor ?? "").ToLowerInvariant(), out var byVendor))
        {
            return byVendor;
        }
        var name = (chip ?? "").ToLowerInvariant();
        foreach (var (generation, contains, pattern) in _nameRules)
        {
            if (contains.Any(text => name.Contains(text)) || (pattern?.IsMatch(name) ?? false))
            {
                return generation;
            }
        }
        return "unknown";
    }

    private string FromPci(IReadOnlyList<PciGpu> displayGpus)
    {
        var amd = false;
        foreach (var gpu in displayGpus)
        {
            _pciVendors.TryGetValue(gpu.Vendor, out var kind);
            if (kind == "intel")
            {
                return "intel";
            }
            if (kind == "amd")
            {
                amd = true;
                if (_amdPci.TryGetValue(gpu.Device, out var generation))
                {
                    return generation;
                }
            }
        }
        // An AMD GPU the table doesn't know yet is newer than the table.
        return amd ? _unknownAmd : "unknown";
    }

    private static IReadOnlyList<DataValue> Array(DataValue? value) =>
        value is DataArray array ? array.Items : throw new DataFormatException("invalid_list");

    private static string Text(DataValue value) =>
        value is DataString { Value.Length: > 0 } text ? text.Value : throw new DataFormatException("invalid_text");

    private static Dictionary<string, string> Map(DataValue? value) => value is DataObject item
        ? item.Members.ToDictionary(member => member.Key.ToLowerInvariant(), member => Text(member.Value), StringComparer.Ordinal)
        : throw new DataFormatException("invalid_mapping");
}
