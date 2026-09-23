using System.Text.Json;
using PanelDeControl.Core.Devices;
using Xunit;

namespace PanelDeControl.Core.Tests;

public sealed class DeviceCatalogContractTests
{
    private static readonly string DevicesDirectory =
        Path.Combine(AppContext.BaseDirectory, "Devices");

    private static DeviceCatalog LoadCatalog()
    {
        return DeviceCatalog.Parse(File.ReadAllText(Path.Combine(DevicesDirectory, "catalog.json")));
    }

    public static IEnumerable<object[]> SharedCases()
    {
        using var document = JsonDocument.Parse(
            File.ReadAllText(Path.Combine(DevicesDirectory, "catalog_cases.json")));
        foreach (var item in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            var input = item.GetProperty("input");
            yield return new object[]
            {
                item.GetProperty("id").GetString()!,
                input.GetProperty("product_name").GetString()!,
                input.GetProperty("sys_vendor").GetString()!,
                input.GetProperty("board_name").GetString()!,
                item.GetProperty("expected").GetProperty("key").GetString()!,
            };
        }
    }

    [Theory]
    [MemberData(nameof(SharedCases))]
    public void SharedCasesMatchLinuxDetection(
        string id,
        string productName,
        string sysVendor,
        string boardName,
        string expectedKey)
    {
        var profile = LoadCatalog().Match(productName, sysVendor, boardName);

        Assert.True(expectedKey == profile.Key, $"{id}: expected {expectedKey}, got {profile.Key}");
    }

    [Fact]
    public void CatalogCarriesIdentityAndLimitsForTheWindowsFleet()
    {
        var catalog = LoadCatalog();

        var allyX = catalog.Profiles.Single(profile => profile.Key == "rog_xbox_ally_x");
        Assert.Equal("ROG Xbox Ally X", allyX.DisplayName);
        Assert.Equal("amd", allyX.Vendor);
        Assert.True(allyX.Limits.TdpMax >= allyX.Limits.TdpMin);

        var claw = catalog.Profiles.Single(profile => profile.Key == "msi_claw_8_ai_plus");
        Assert.Equal("intel", claw.Vendor);

        Assert.True(catalog.Generic.IsGeneric);
        Assert.DoesNotContain(catalog.Profiles, profile => profile.IsGeneric);
    }

    [Fact]
    public void UnsupportedSchemaIsRejected()
    {
        var json = File.ReadAllText(Path.Combine(DevicesDirectory, "catalog.json"))
            .Replace("\"schema_version\": 1", "\"schema_version\": 2");

        Assert.Throws<InvalidDataException>(() => DeviceCatalog.Parse(json));
    }
}
