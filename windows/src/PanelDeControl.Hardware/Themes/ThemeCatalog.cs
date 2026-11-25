using System.Text.Json;
using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

public sealed record ThemeArtifact(Uri Url, long Size, string Sha256);

public sealed record ThemeRelease(
    string CatalogId,
    string CssLoaderName,
    string Version,
    IReadOnlyDictionary<string, string> DisplayName,
    IReadOnlyDictionary<string, string> Description,
    string Author,
    ThemeArtifact Artifact,
    string? ExclusiveGroup);

public sealed record ThemeEarlyArtifact(string Version, long Size, string Sha256);

/// <summary>
/// A theme's early channel from <c>themes/v1/early.json</c>: no download URL, only the exact
/// archives that were published, identified by size and SHA-256.
/// </summary>
public sealed record ThemeEarlyRelease(
    string CatalogId,
    string CssLoaderName,
    string Version,
    IReadOnlyDictionary<string, string> DisplayName,
    IReadOnlyDictionary<string, string> Description,
    string Author,
    IReadOnlyList<ThemeEarlyArtifact> Artifacts)
{
    public ThemeRelease AsRelease(ThemeEarlyArtifact artifact) => new(
        CatalogId,
        CssLoaderName,
        artifact.Version,
        DisplayName,
        Description,
        Author,
        new ThemeArtifact(ThemeCatalog.EarlyCatalogUrl, artifact.Size, artifact.Sha256),
        null);
}

/// <summary>
/// The official catalog published at <c>themes/v1/catalog.json</c>, parsed with the same limits as
/// the Linux backend. Windows ignores the Linux minimum versions: compatibility here is the
/// manifest subset and the runtime ABI, both checked again at install time.
/// </summary>
public static class ThemeCatalog
{
    public const string OfficialBaseUrl = "https://hooandee.github.io/panel-de-control";
    public const string CatalogPath = "themes/v1/catalog.json";
    public const string EarlyCatalogPath = "themes/v1/early.json";
    private const int MaximumEarlyArtifacts = 8;
    public const int MaximumMetadataBytes = 64 * 1024;
    public const long MaximumArtifactBytes = 64L * 1024 * 1024;

    private const int MaximumEntries = 32;
    private static readonly Regex SafeId = new("^[a-z0-9]+(?:-[a-z0-9]+)*$", RegexOptions.CultureInvariant);
    private static readonly Regex StableVersion = new(@"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$", RegexOptions.CultureInvariant);
    private static readonly Regex Sha256Hex = new("^[a-f0-9]{64}$", RegexOptions.CultureInvariant);

    public static Uri CatalogUrl { get; } = new($"{OfficialBaseUrl}/{CatalogPath}");

    public static Uri EarlyCatalogUrl { get; } = new($"{OfficialBaseUrl}/{EarlyCatalogPath}");

    public static IReadOnlyList<ThemeEarlyRelease> ParseEarly(byte[] payload)
    {
        if (payload.Length > MaximumMetadataBytes)
        {
            throw new FormatException("Early catalog is too large");
        }

        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            if (root.GetProperty("schemaVersion").GetInt32() != 1)
            {
                throw new FormatException("Early catalog schema is unsupported");
            }

            var themes = root.GetProperty("themes").EnumerateArray().Select(ParseEarlyRelease).ToArray();
            if (themes.Length > MaximumEntries || themes.Select(theme => theme.CatalogId).Distinct().Count() != themes.Length)
            {
                throw new FormatException("Early catalog entries are invalid");
            }

            return themes;
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            throw new FormatException("Early catalog is invalid", exception);
        }
    }

    private static ThemeEarlyRelease ParseEarlyRelease(JsonElement release)
    {
        if (release.GetProperty("schemaVersion").GetInt32() != 1)
        {
            throw new FormatException("Early theme schema is unsupported");
        }

        var catalogId = release.GetProperty("catalogId").GetString() ?? string.Empty;
        var name = release.GetProperty("cssLoaderName").GetString() ?? string.Empty;
        var author = release.GetProperty("author").GetString() ?? string.Empty;
        var early = release.GetProperty("early");
        var version = early.GetProperty("version").GetString() ?? string.Empty;
        var artifacts = early.GetProperty("artifacts").EnumerateArray().Select(artifact => new ThemeEarlyArtifact(
            artifact.GetProperty("version").GetString() ?? string.Empty,
            artifact.GetProperty("size").GetInt64(),
            artifact.GetProperty("sha256").GetString() ?? string.Empty)).ToArray();
        if (!SafeId.IsMatch(catalogId)
            || !ThemeManifest.IsSafeName(name)
            || !StableVersion.IsMatch(version)
            || author.Trim().Length == 0
            || author.Length > 80
            || artifacts.Length == 0
            || artifacts.Length > MaximumEarlyArtifacts
            || artifacts.Any(artifact => !StableVersion.IsMatch(artifact.Version) || artifact.Size <= 0 || artifact.Size > MaximumArtifactBytes || !Sha256Hex.IsMatch(artifact.Sha256))
            || artifacts.Select(artifact => artifact.Version).Distinct().Count() != artifacts.Length
            || artifacts.Select(artifact => artifact.Sha256).Distinct().Count() != artifacts.Length
            || artifacts.All(artifact => artifact.Version != version))
        {
            throw new FormatException($"Early theme {catalogId} is invalid");
        }

        return new ThemeEarlyRelease(
            catalogId,
            name,
            version,
            Localized(release.GetProperty("displayName"), 80),
            Localized(release.GetProperty("description"), 400),
            author,
            artifacts);
    }

    public static int CompareVersions(string left, string right)
    {
        var a = left.Split('.').Select(int.Parse).ToArray();
        var b = right.Split('.').Select(int.Parse).ToArray();
        for (var index = 0; index < 3; index++)
        {
            var order = a[index].CompareTo(b[index]);
            if (order != 0)
            {
                return order;
            }
        }

        return 0;
    }

    public static IReadOnlyList<ThemeRelease> Parse(byte[] payload)
    {
        if (payload.Length > MaximumMetadataBytes)
        {
            throw new FormatException("Catalog is too large");
        }

        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            if (root.GetProperty("schemaVersion").GetInt32() != 1)
            {
                throw new FormatException("Catalog schema is unsupported");
            }

            var themes = root.GetProperty("themes").EnumerateArray().Select(ParseRelease).ToArray();
            if (themes.Length > MaximumEntries
                || themes.Select(theme => theme.CatalogId).Distinct().Count() != themes.Length
                || themes.Select(theme => theme.CssLoaderName).Distinct().Count() != themes.Length)
            {
                throw new FormatException("Catalog entries are invalid");
            }

            return themes;
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            throw new FormatException("Catalog is invalid", exception);
        }
    }

    public static Uri ArtifactUrl(string catalogId, string version) =>
        new($"{OfficialBaseUrl}/themes/v1/{catalogId}/{version}/theme.zip");

    private static ThemeRelease ParseRelease(JsonElement release)
    {
        if (release.GetProperty("schemaVersion").GetInt32() != 1)
        {
            throw new FormatException("Release schema is unsupported");
        }

        var catalogId = release.GetProperty("catalogId").GetString() ?? string.Empty;
        var name = release.GetProperty("cssLoaderName").GetString() ?? string.Empty;
        var version = release.GetProperty("version").GetString() ?? string.Empty;
        var author = release.GetProperty("author").GetString() ?? string.Empty;
        var artifact = release.GetProperty("artifact");
        var url = artifact.GetProperty("url").GetString() ?? string.Empty;
        var size = artifact.GetProperty("size").GetInt64();
        var sha = artifact.GetProperty("sha256").GetString() ?? string.Empty;
        string? exclusiveGroup = release.TryGetProperty("exclusiveGroup", out var group) ? group.GetString() : null;
        if (!SafeId.IsMatch(catalogId)
            || !ThemeManifest.IsSafeName(name)
            || !StableVersion.IsMatch(version)
            || author.Trim().Length == 0
            || author.Length > 80
            || size <= 0
            || size > MaximumArtifactBytes
            || !Sha256Hex.IsMatch(sha)
            || url != ArtifactUrl(catalogId, version).AbsoluteUri
            || (exclusiveGroup is not null && !SafeId.IsMatch(exclusiveGroup)))
        {
            throw new FormatException($"Release {catalogId} is invalid");
        }

        return new ThemeRelease(
            catalogId,
            name,
            version,
            Localized(release.GetProperty("displayName"), 80),
            Localized(release.GetProperty("description"), 400),
            author,
            new ThemeArtifact(new Uri(url), size, sha),
            exclusiveGroup);
    }

    private static IReadOnlyDictionary<string, string> Localized(JsonElement element, int maximumLength)
    {
        var text = element.EnumerateObject().ToDictionary(
            language => language.Name,
            language => language.Value.GetString() ?? string.Empty,
            StringComparer.Ordinal);
        if (!text.ContainsKey("en") || text.Values.Any(value => value.Trim().Length == 0 || value.Length > maximumLength))
        {
            throw new FormatException("Localized text is invalid");
        }

        return text;
    }
}
