using System.Text.Json.Nodes;
using PanelDeControl.Core.Upscalers;
using Xunit;

namespace PanelDeControl.Core.Tests.Upscalers;

/// <summary>The GPU family must match device_registry.gpu_facts for every case tests/test_gpu_generation_parity.py writes.</summary>
public sealed class GpuFamilyParityTests
{
    private static readonly JsonObject Fixture = JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "Upscalers", "gpu_generations.json")))!.AsObject();
    private static readonly GpuFamily Rules = GpuFamily.Parse(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Data", "Upscalers", "gpus.json")));

    [Fact]
    public void EveryCaseMatchesTheLinuxBackend()
    {
        var failures = new List<string>();
        foreach (var node in Fixture["cases"]!.AsArray())
        {
            var gpus = Fixture["pci_sets"]![node!["pci"]!.GetValue<string>()]!.AsArray()
                .Select(card => new PciGpu(card![0]!.GetValue<string>(), card[1]!.GetValue<string>())).ToList();
            var result = Rules.Detect(node["vendor"]!.GetValue<string>(), node["chip"]!.GetValue<string>(), gpus);
            if (result.Generation != node["generation"]!.GetValue<string>() || result.Source != node["source"]!.GetValue<string>())
            {
                failures.Add($"{node.ToJsonString()} -> {result.Generation}/{result.Source}");
            }
        }
        Assert.True(failures.Count == 0, string.Join("\n", failures.Take(5)));
    }

    [Theory]
    [InlineData(@"PCI\VEN_1002&DEV_150E&SUBSYS_1F4C1043&REV_C1\4&2A3B1C&0&0041", "0x1002", "0x150e")]
    [InlineData(@"PCI\VEN_10DE&DEV_2684&SUBSYS_88EE1043&REV_A1", "0x10de", "0x2684")]
    public void ReadsPciIdsFromWindowsDeviceIds(string pnp, string vendor, string device)
    {
        var gpu = GpuFamily.FromPnpId(pnp);
        Assert.Equal(vendor, gpu!.Vendor);
        Assert.Equal(device, gpu.Device);
    }

    [Theory]
    [InlineData(@"ROOT\BasicDisplay\0000")]
    [InlineData(@"SWD\RemoteDisplayEnum\RdpIdd_IndirectDisplay")]
    [InlineData(null)]
    public void IgnoresDisplaysThatAreNotPciGpus(string? pnp) => Assert.Null(GpuFamily.FromPnpId(pnp));

    [Fact]
    public void ZTwoExtremeOnWindowsIsRdnaThreeFive()
    {
        var result = Rules.Detect(GpuFamily.CpuVendor("AuthenticAMD"), "AMD Ryzen Z2 Extreme w/ Radeon 890M", new[] { GpuFamily.FromPnpId(@"PCI\VEN_1002&DEV_150E")! });
        Assert.Equal("rdna35", result.Generation);
        Assert.Equal("name", result.Source);
    }

    [Fact]
    public void WithoutRulesEveryGpuIsUnknown()
    {
        var result = GpuFamily.None.Detect("amd", "AMD Ryzen Z2 Extreme", new[] { new PciGpu("0x1002", "0x150e") });
        Assert.Equal("unknown", result.Generation);
    }
}
