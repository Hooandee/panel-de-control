using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

public sealed record ThemeExtensionDeclaration(int AbiVersion, string Entrypoint, long Size, string Sha256);

public sealed record LocalizedPatchLabel(
    IReadOnlyDictionary<string, string> Name,
    IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Values);

/// <summary>
/// <c>panel-theme.json</c>: the Panel identity of a CSS Loader theme folder.
/// </summary>
public sealed class PanelThemeMarker
{
    public const string FileName = "panel-theme.json";
    public const string ExtensionEntrypoint = "panel-extension.js";
    public const long MaximumExtensionBytes = 2 * 1024 * 1024;

    private static readonly Regex CatalogId = new("^[a-z0-9]+(?:-[a-z0-9]+)*$", RegexOptions.CultureInvariant);
    private static readonly Regex Sha256Hex = new("^[a-f0-9]{64}$", RegexOptions.CultureInvariant);
    private static readonly int[] SupportedAbiVersions = { 1, 2 };

    private PanelThemeMarker(
        string catalogId,
        IReadOnlyDictionary<string, LocalizedPatchLabel> labels,
        ThemeExtensionDeclaration? extension)
    {
        CatalogIdentity = catalogId;
        Labels = labels;
        Extension = extension;
    }

    public string CatalogIdentity { get; }

    public IReadOnlyDictionary<string, LocalizedPatchLabel> Labels { get; }

    public ThemeExtensionDeclaration? Extension { get; }

    public static bool IsCatalogId(string value) => CatalogId.IsMatch(value);

    public static PanelThemeMarker Parse(string json)
    {
        try
        {
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            var schema = root.GetProperty("schemaVersion").GetInt32();
            var catalogId = root.GetProperty("catalogId").GetString() ?? string.Empty;
            if ((schema != 1 && schema != 2) || !IsCatalogId(catalogId))
            {
                throw new ThemeManifestException("panel-theme.json identity is invalid");
            }

            var extension = root.TryGetProperty("extension", out var declared)
                ? ParseExtension(declared)
                : null;
            if (extension is not null && schema != 2)
            {
                throw new ThemeManifestException("Theme extensions need panel-theme schema 2");
            }

            var labels = root.TryGetProperty("labels", out var labelElement)
                ? ParseLabels(labelElement)
                : new Dictionary<string, LocalizedPatchLabel>();
            return new PanelThemeMarker(catalogId, labels, extension);
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            throw new ThemeManifestException("panel-theme.json is invalid");
        }
    }

    public bool ExtensionMatches(byte[] source) =>
        Extension is { } extension
        && source.LongLength == extension.Size
        && Convert.ToHexString(SHA256.HashData(source)).ToLowerInvariant() == extension.Sha256;

    private static ThemeExtensionDeclaration ParseExtension(JsonElement element)
    {
        var abi = element.GetProperty("abiVersion").GetInt32();
        var entrypoint = element.GetProperty("entrypoint").GetString();
        var size = element.GetProperty("size").GetInt64();
        var sha = element.GetProperty("sha256").GetString() ?? string.Empty;
        if (!SupportedAbiVersions.Contains(abi)
            || entrypoint != ExtensionEntrypoint
            || size <= 0
            || size > MaximumExtensionBytes
            || !Sha256Hex.IsMatch(sha))
        {
            throw new ThemeManifestException("Theme extension declaration is invalid");
        }

        return new ThemeExtensionDeclaration(abi, entrypoint, size, sha);
    }

    // Labels are cosmetic: a label this version does not understand is dropped, never fatal.
    private static IReadOnlyDictionary<string, LocalizedPatchLabel> ParseLabels(JsonElement element)
    {
        var labels = new Dictionary<string, LocalizedPatchLabel>(StringComparer.Ordinal);
        if (element.ValueKind != JsonValueKind.Object)
        {
            return labels;
        }

        foreach (var patch in element.EnumerateObject())
        {
            if (patch.Value.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            var name = patch.Value.TryGetProperty("name", out var nameElement)
                ? LocalizedText(nameElement)
                : new Dictionary<string, string>();
            var values = new Dictionary<string, IReadOnlyDictionary<string, string>>(StringComparer.Ordinal);
            if (patch.Value.TryGetProperty("values", out var valueElement) && valueElement.ValueKind == JsonValueKind.Object)
            {
                foreach (var value in valueElement.EnumerateObject())
                {
                    values[value.Name] = LocalizedText(value.Value);
                }
            }

            labels[patch.Name] = new LocalizedPatchLabel(name, values);
        }

        return labels;
    }

    private static IReadOnlyDictionary<string, string> LocalizedText(JsonElement element)
    {
        var text = new Dictionary<string, string>(StringComparer.Ordinal);
        if (element.ValueKind != JsonValueKind.Object)
        {
            return text;
        }

        foreach (var language in element.EnumerateObject())
        {
            if (language.Value.ValueKind == JsonValueKind.String && language.Name.Length <= 8)
            {
                var value = language.Value.GetString()!;
                if (value.Length is > 0 and <= 120)
                {
                    text[language.Name] = value;
                }
            }
        }

        return text;
    }
}
