using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ThemeManifestTests
{
    private const string Eclipse = """
        {
          "name": "Hooandee Eclipse",
          "display_name": "Eclipse",
          "author": "Hooandee",
          "version": "0.2.5",
          "description": "Negro OLED",
          "target": "System-Wide",
          "manifest_version": 9,
          "inject": {
            "tokens.css": ["bigpicture", "QuickAccess", "MainMenu", "notificationtoasts.*"],
            "home.css": ["bigpicture"]
          },
          "patches": {
            "Acento": {
              "default": "Venus",
              "type": "dropdown",
              "values": {
                "Venus": {},
                "Marte": { "options/accent-mars.css": ["bigpicture", "QuickAccess"] }
              }
            },
            "Movimiento": {
              "default": "Yes",
              "type": "checkbox",
              "values": { "No": { "options/motion-off.css": ["bigpicture"] }, "Yes": {} }
            }
          }
        }
        """;

    [Fact]
    public void ParsesInjectsAndPatchesInDeclarationOrder()
    {
        var manifest = ThemeManifest.Parse(Eclipse);

        Assert.Equal("Hooandee Eclipse", manifest.Name);
        Assert.Equal("Eclipse", manifest.DisplayName);
        Assert.Equal("0.2.5", manifest.Version);
        Assert.Equal(new[] { "tokens.css", "home.css" }, manifest.Injects.Select(inject => inject.File));
        Assert.Equal(new[] { "bigpicture", "QuickAccess", "MainMenu", "notificationtoasts.*" }, manifest.Injects[0].Targets);
        Assert.Equal(new[] { "Acento", "Movimiento" }, manifest.Patches.Select(patch => patch.Name));
        var accent = manifest.Patches[0];
        Assert.Equal(ThemePatchType.Dropdown, accent.Type);
        Assert.Equal("Venus", accent.DefaultValue);
        Assert.Equal(new[] { "Venus", "Marte" }, accent.Options.Select(option => option.Value));
        Assert.Empty(accent.Options[0].Injects);
        Assert.Equal("options/accent-mars.css", accent.Options[1].Injects[0].File);
    }

    [Theory]
    [InlineData("""{"name":"X","version":"1.0.0","inject":{"../evil.css":["bigpicture"]}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","inject":{"C:/evil.css":["bigpicture"]}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","inject":{"evil.js":["bigpicture"]}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","inject":{"a.css":[]}}""")]
    [InlineData("""{"name":"","version":"1.0.0","inject":{}}""")]
    [InlineData("""{"name":"X/Y","version":"1.0.0","inject":{}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","patches":{"P":{"default":"Z","type":"dropdown","values":{"A":{}}}}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","patches":{"P":{"default":"A","type":"colorpicker","values":{"A":{}}}}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","patches":{"P":{"default":"A","type":"dropdown","values":{"A":{}},"components":[]}}}""")]
    [InlineData("""{"name":"X","version":"1.0.0","dependencies":{"Other":{}}}""")]
    [InlineData("""not json""")]
    public void RejectsUnsafeOrUnsupportedManifests(string json)
    {
        Assert.Throws<ThemeManifestException>(() => ThemeManifest.Parse(json));
    }

    [Fact]
    public void MissingTypeDefaultsToDropdownLikeCssLoader()
    {
        var manifest = ThemeManifest.Parse("""{"name":"X","version":"1.0.0","patches":{"P":{"default":"A","values":{"A":{},"B":{}}}}}""");

        Assert.Equal(ThemePatchType.Dropdown, manifest.Patches[0].Type);
    }

    [Fact]
    public void ResolvesActiveInjectsForChosenPatchValues()
    {
        var manifest = ThemeManifest.Parse(Eclipse);
        var values = new Dictionary<string, string> { ["Acento"] = "Marte", ["Movimiento"] = "Unknown" };

        var files = manifest.ActiveInjects(values).Select(inject => inject.File).ToArray();

        Assert.Equal(new[] { "tokens.css", "home.css", "options/accent-mars.css" }, files);
    }
}
