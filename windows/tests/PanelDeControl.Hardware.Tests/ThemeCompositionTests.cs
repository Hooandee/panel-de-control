using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ThemeCompositionTests
{
    private static readonly IReadOnlySet<string> NoClasses = new HashSet<string>();

    private static SteamTarget BigPicture => new(
        "bp",
        "Modo Big Picture de Steam",
        "about:blank?createflags=6292754&browserType=3&useragent=Valve%20Steam%20Gamepad",
        NoClasses);

    private static SteamTarget Target(string title, string url = "about:blank", params string[] classes) =>
        new(title, title, url, new HashSet<string>(classes));

    [Fact]
    public void BigPictureIsFoundByUrlWhateverTheLocalizedTitle()
    {
        Assert.True(ThemeTargetMatcher.Matches(BigPicture, "bigpicture"));
        Assert.True(ThemeTargetMatcher.Matches(BigPicture, "SP"));
        Assert.True(ThemeTargetMatcher.Matches(BigPicture, "All"));
        Assert.False(ThemeTargetMatcher.Matches(Target("SharedJSContext"), "bigpicture"));
    }

    [Theory]
    [InlineData("QuickAccess_uid2", "QuickAccess", true)]
    [InlineData("QuickAccess_uid2", "bigpictureoverlay", true)]
    [InlineData("MainMenu_uid2", "MainMenu", true)]
    [InlineData("MainMenu_uid2", "All", true)]
    [InlineData("notificationtoasts_uid2", "notificationtoasts.*", true)]
    [InlineData("notificationtoasts_uid2", "desktoppopup", true)]
    [InlineData("SharedJSContext", "QuickAccess", false)]
    [InlineData("Steam", "desktop", true)]
    [InlineData("anything", "([", false)]
    public void TitlesFollowCssLoaderAliases(string title, string selector, bool expected)
    {
        Assert.Equal(expected, ThemeTargetMatcher.Matches(Target(title), selector));
    }

    [Fact]
    public void ClassAndUrlSelectorsMatch()
    {
        var friends = Target("Friends", "https://steamloopback.host/friends", "friendsui-container");

        Assert.True(ThemeTargetMatcher.Matches(friends, "desktopchat"));
        Assert.True(ThemeTargetMatcher.Matches(friends, "~steamloopback.host/friends~"));
        Assert.False(ThemeTargetMatcher.Matches(Target("Friends"), "desktopchat"));
    }

    [Fact]
    public void ComposesSheetsPerPageInThemeThenManifestOrder()
    {
        var eclipse = Theme("""
            {"name":"Eclipse","version":"1.0.0",
             "inject":{"tokens.css":["bigpicture","QuickAccess"],"home.css":["bigpicture"]},
             "patches":{"Acento":{"default":"A","type":"dropdown","values":{"A":{},"B":{"accent-b.css":["QuickAccess"]}}}}}
            """);
        var other = Theme("""{"name":"Other","version":"1.0.0","inject":{"tokens.css":["QuickAccess"]}}""");
        var enabled = new[]
        {
            new ThemeSelection(eclipse, new Dictionary<string, string> { ["Acento"] = "B" }),
            new ThemeSelection(other, new Dictionary<string, string>()),
        };

        var bigPicture = ThemeComposer.SheetsFor(BigPicture, enabled).Select(sheet => sheet.Id);
        var quickAccess = ThemeComposer.SheetsFor(Target("QuickAccess_uid2"), enabled).Select(sheet => sheet.Id);

        Assert.Equal(new[] { "pdc-theme:Eclipse:tokens.css", "pdc-theme:Eclipse:home.css" }, bigPicture);
        Assert.Equal(new[] { "pdc-theme:Eclipse:tokens.css", "pdc-theme:Eclipse:accent-b.css", "pdc-theme:Other:tokens.css" }, quickAccess);
    }

    [Fact]
    public void TranslatesToTheClassThatExistsInTheRunningClient()
    {
        var table = ClassTranslator.ParseTable("""
            {
              "a": ["DialogCheckbox_Container", "_old111", "_new222"],
              "b": ["Menu_Item", "_live333", "_future444"],
              "c": ["single"]
            }
            """);
        var translator = ClassTranslator.Create(table, new HashSet<string> { "_new222", "_live333" });

        var css = translator.Translate(".DialogCheckbox_Container > ._old111, .Menu_Item:focus, [class*=\"_future444\"], .single, .5em");

        Assert.Equal("._new222 > ._new222, ._live333:focus, [class*=\"_live333\"], .single, .5em", css);
    }

    [Fact]
    public void WithoutLiveClassesTheNewestNameWins()
    {
        var table = ClassTranslator.ParseTable("""{"b": ["Menu_Item", "_live333", "_future444"]}""");

        Assert.Equal("._future444", ClassTranslator.Create(table, null).Translate(".Menu_Item"));
        Assert.Equal(".Menu_Item", ClassTranslator.Identity.Translate(".Menu_Item"));
    }

    [Fact]
    public void FingerprintChangesWithTheLiveClient()
    {
        var table = ClassTranslator.ParseTable("""{"b": ["Menu_Item", "_live333", "_future444"]}""");

        Assert.NotEqual(
            ClassTranslator.Create(table, new HashSet<string> { "_live333" }).Fingerprint,
            ClassTranslator.Create(table, new HashSet<string> { "_future444" }).Fingerprint);
    }

    [Fact]
    public void PanelMarkerReadsLabelsAndVerifiesTheExtension()
    {
        var source = "module.exports = {};"u8.ToArray();
        var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(source)).ToLowerInvariant();
        var marker = PanelThemeMarker.Parse($$$$"""
            {"schemaVersion":2,"catalogId":"hooandee-eclipse",
             "labels":{"Acento":{"name":{"es":"Color del tema","en":"Theme color"},"values":{"Venus":{"en":"Venus"}}},"Broken":5},
             "extension":{"abiVersion":2,"entrypoint":"panel-extension.js","size":{{{{source.Length}}}},"sha256":"{{{{sha}}}}"}}
            """);

        Assert.Equal("hooandee-eclipse", marker.CatalogIdentity);
        Assert.Equal("Theme color", marker.Labels["Acento"].Name["en"]);
        Assert.Equal("Venus", marker.Labels["Acento"].Values["Venus"]["en"]);
        Assert.False(marker.Labels.ContainsKey("Broken"));
        Assert.True(marker.ExtensionMatches(source));
        Assert.False(marker.ExtensionMatches("tampered"u8.ToArray()));
    }

    [Theory]
    [InlineData("""{"schemaVersion":3,"catalogId":"x"}""")]
    [InlineData("""{"schemaVersion":2,"catalogId":"Bad Id"}""")]
    [InlineData("""{"schemaVersion":1,"catalogId":"x","extension":{"abiVersion":2,"entrypoint":"panel-extension.js","size":1,"sha256":"0000000000000000000000000000000000000000000000000000000000000000"}}""")]
    [InlineData("""{"schemaVersion":2,"catalogId":"x","extension":{"abiVersion":9,"entrypoint":"panel-extension.js","size":1,"sha256":"0000000000000000000000000000000000000000000000000000000000000000"}}""")]
    [InlineData("""{"schemaVersion":2,"catalogId":"x","extension":{"abiVersion":2,"entrypoint":"../x.js","size":1,"sha256":"0000000000000000000000000000000000000000000000000000000000000000"}}""")]
    public void PanelMarkerFailsClosed(string json)
    {
        Assert.Throws<ThemeManifestException>(() => PanelThemeMarker.Parse(json));
    }

    private static InstalledTheme Theme(string manifest) =>
        new(ThemeManifest.Parse(manifest), null, "/themes/x");
}
