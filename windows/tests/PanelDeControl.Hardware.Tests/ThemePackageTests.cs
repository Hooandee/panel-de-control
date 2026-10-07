using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using PanelDeControl.Hardware.Themes;
using Xunit;

namespace PanelDeControl.Hardware.Tests;

public sealed class ThemePackageTests : IDisposable
{
    private const string Name = "Hooandee Eclipse";
    private const string Extension = "module.exports = Object.freeze({abiVersion: 2, mount: () => () => {}});";

    private readonly string root = Path.Combine(Path.GetTempPath(), $"pdc-themes-{Guid.NewGuid():N}");

    public void Dispose()
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void ParsesTheOfficialCatalogShape()
    {
        var releases = ThemeCatalog.Parse(Encoding.UTF8.GetBytes(Catalog("0.2.5", 62848, new string('c', 64))));

        var eclipse = Assert.Single(releases);
        Assert.Equal("hooandee-eclipse", eclipse.CatalogId);
        Assert.Equal(Name, eclipse.CssLoaderName);
        Assert.Equal("Eclipse", eclipse.DisplayName["es"]);
        Assert.Equal(62848, eclipse.Artifact.Size);
    }

    [Theory]
    [InlineData("https://evil.example/themes/v1/hooandee-eclipse/0.2.5/theme.zip")]
    [InlineData("http://hooandee.github.io/panel-de-control/themes/v1/hooandee-eclipse/0.2.5/theme.zip")]
    [InlineData("https://hooandee.github.io/panel-de-control/themes/v1/hooandee-eclipse/0.2.4/theme.zip")]
    public void RejectsArtifactsOutsideTheOfficialChannel(string url)
    {
        var json = Catalog("0.2.5", 10, new string('c', 64)).Replace(
            "https://hooandee.github.io/panel-de-control/themes/v1/hooandee-eclipse/0.2.5/theme.zip",
            url);

        Assert.Throws<FormatException>(() => ThemeCatalog.Parse(Encoding.UTF8.GetBytes(json)));
    }

    [Fact]
    public void ComparesVersionsNumerically()
    {
        Assert.True(ThemeCatalog.CompareVersions("0.10.0", "0.9.55") > 0);
        Assert.Equal(0, ThemeCatalog.CompareVersions("1.1.2", "1.1.2"));
    }

    [Fact]
    public void InstallsAVerifiedPackageAndReplacesThePreviousVersion()
    {
        var installer = new ThemePackageInstaller(root);
        var first = Package("0.2.4");
        installer.Install(Release("0.2.4", first), first);
        var second = Package("0.2.5");

        var installed = installer.Install(Release("0.2.5", second), second);

        Assert.Equal("0.2.5", installed.Manifest.Version);
        Assert.Equal("hooandee-eclipse", installed.Marker!.CatalogIdentity);
        Assert.Equal(Extension, ThemeLibrary.ReadExtension(installed));
        Assert.True(File.Exists(Path.Combine(root, Name, "icons", "chat.png")));
        Assert.Equal(new[] { Name }, Directory.GetDirectories(root).Select(Path.GetFileName));
        Assert.Equal("0.2.5", ThemeLibrary.Scan(root).Themes.Single().Manifest.Version);
    }

    [Fact]
    public void RejectsATamperedDownloadAndKeepsTheInstalledVersion()
    {
        var installer = new ThemePackageInstaller(root);
        var good = Package("0.2.4");
        installer.Install(Release("0.2.4", good), good);
        var update = Package("0.2.5");
        var release = Release("0.2.5", update);
        update[^10] ^= 0xFF;

        var error = Assert.Throws<ThemeInstallException>(() => installer.Install(release, update));

        Assert.Equal("artifact_hash_mismatch", error.Code);
        Assert.Equal("0.2.4", ThemeLibrary.Scan(root).Themes.Single().Manifest.Version);
    }

    [Theory]
    [InlineData("Other/theme.json", "unsafe_archive")]
    [InlineData("Hooandee Eclipse/../escape.css", "unsafe_archive")]
    [InlineData("/Hooandee Eclipse/abs.css", "unsafe_archive")]
    public void RejectsEntriesOutsideTheThemeRoot(string entry, string code)
    {
        var archive = Package("0.2.5", (entry, "x"));
        var installer = new ThemePackageInstaller(root);

        var error = Assert.Throws<ThemeInstallException>(() => installer.Install(Release("0.2.5", archive), archive));

        Assert.Equal(code, error.Code);
        Assert.False(Directory.Exists(Path.Combine(root, Name)));
    }

    [Fact]
    public void RejectsAPackageWhoseIdentityDiffersFromTheCatalog()
    {
        var archive = Package("0.2.6");
        var installer = new ThemePackageInstaller(root);

        var error = Assert.Throws<ThemeInstallException>(() => installer.Install(Release("0.2.5", archive), archive));

        Assert.Equal("identity_mismatch", error.Code);
    }

    [Fact]
    public void RejectsAnUndeclaredOrAlteredExtension()
    {
        var archive = Package("0.2.5", ($"{Name}/panel-extension.js", Extension + "//changed"));
        var installer = new ThemePackageInstaller(root);

        var error = Assert.Throws<ThemeInstallException>(() => installer.Install(Release("0.2.5", archive), archive));

        Assert.Equal("invalid_package", error.Code);
    }

    [Fact]
    public void RecoversThePreviousVersionAfterAnInterruptedSwap()
    {
        var installer = new ThemePackageInstaller(root);
        var good = Package("0.2.4");
        installer.Install(Release("0.2.4", good), good);
        var transaction = Path.Combine(root, ".install-interrupted");
        Directory.CreateDirectory(transaction);
        Directory.Move(Path.Combine(root, Name), Path.Combine(transaction, ".previous"));

        ThemePackageInstaller.RecoverInterruptedInstalls(root);

        Assert.Equal("0.2.4", ThemeLibrary.Scan(root).Themes.Single().Manifest.Version);
        Assert.False(Directory.Exists(transaction));
    }

    [Fact]
    public void ScanReportsBrokenFoldersWithoutFailing()
    {
        Directory.CreateDirectory(Path.Combine(root, "Broken"));
        File.WriteAllText(Path.Combine(root, "Broken", "theme.json"), "{");
        Directory.CreateDirectory(Path.Combine(root, "Renamed"));
        File.WriteAllText(Path.Combine(root, "Renamed", "theme.json"), """{"name":"Other","version":"1.0.0"}""");

        var snapshot = ThemeLibrary.Scan(root);

        Assert.Empty(snapshot.Themes);
        Assert.Equal(new[] { "invalid_manifest", "identity_mismatch" }, snapshot.Broken.Select(broken => broken.Reason));
    }

    [Fact]
    public void SettingsRoundTripInOrder()
    {
        var store = new ThemeSettingsStore(root);
        store.Write(new[]
        {
            new ThemeSetting(Name, true, new Dictionary<string, string> { ["Acento"] = "Marte" }),
            new ThemeSetting("Hooandee Gallery", false, new Dictionary<string, string>()),
        });

        var settings = new ThemeSettingsStore(root).Read();

        Assert.Equal(new[] { Name, "Hooandee Gallery" }, settings.Select(setting => setting.Name));
        Assert.True(settings[0].Enabled);
        Assert.Equal("Marte", settings[0].Patches["Acento"]);
    }

    [Fact]
    public void CorruptSettingsReadAsEmpty()
    {
        Directory.CreateDirectory(root);
        File.WriteAllText(Path.Combine(root, ThemeSettingsStore.FileName), "{ nope");

        Assert.Empty(new ThemeSettingsStore(root).Read());
    }

    private static string Catalog(string version, long size, string sha) => $$"""
        {"schemaVersion":1,"themes":[{
          "schemaVersion":1,"catalogId":"hooandee-eclipse","cssLoaderName":"{{Name}}","version":"{{version}}",
          "displayName":{"es":"Eclipse","en":"Eclipse","it":"Eclipse"},
          "description":{"es":"Espacio","en":"Space","it":"Spazio"},
          "author":"Hooandee","tags":[],
          "artifact":{"url":"https://hooandee.github.io/panel-de-control/themes/v1/hooandee-eclipse/{{version}}/theme.zip","size":{{size}},"sha256":"{{sha}}"},
          "minimumVersions":{"panel":"0.56.0","cssLoader":"2.1.2","cssLoaderBackend":9}
        }]}
        """;

    private static ThemeRelease Release(string version, byte[] archive)
    {
        var sha = Convert.ToHexString(SHA256.HashData(archive)).ToLowerInvariant();
        return ThemeCatalog.Parse(Encoding.UTF8.GetBytes(Catalog(version, archive.Length, sha))).Single();
    }

    private static byte[] Package(string version, params (string Path, string Content)[] extra)
    {
        var extension = Encoding.UTF8.GetBytes(Extension);
        var sha = Convert.ToHexString(SHA256.HashData(extension)).ToLowerInvariant();
        var files = new List<(string Path, string Content)>
        {
            ($"{Name}/theme.json", $$$"""{"name":"{{{Name}}}","version":"{{{version}}}","inject":{"tokens.css":["bigpicture"]}}"""),
            ($"{Name}/panel-theme.json", $$$"""{"schemaVersion":2,"catalogId":"hooandee-eclipse","extension":{"abiVersion":2,"entrypoint":"panel-extension.js","size":{{{extension.Length}}},"sha256":"{{{sha}}}"}}"""),
            ($"{Name}/tokens.css", ":root{--x:1}"),
            ($"{Name}/icons/chat.png", "png"),
        };
        if (!extra.Any(file => file.Path.EndsWith("panel-extension.js", StringComparison.Ordinal)))
        {
            files.Add(($"{Name}/panel-extension.js", Extension));
        }

        files.AddRange(extra);
        using var buffer = new MemoryStream();
        using (var zip = new ZipArchive(buffer, ZipArchiveMode.Create, leaveOpen: true))
        {
            foreach (var (path, content) in files)
            {
                using var writer = new StreamWriter(zip.CreateEntry(path).Open());
                writer.Write(content);
            }
        }

        return buffer.ToArray();
    }
}
