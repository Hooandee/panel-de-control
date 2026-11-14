using System.Text;
using System.Text.RegularExpressions;
using PanelDeControl.Core.FileSystem;

namespace PanelDeControl.Core.Upscalers;

/// <summary>Whose upscaler sits beside the exe when Panel de Control did not install it: HelixSR or OptiScaler.</summary>
public static class ForeignUpscalerIdentity
{
    public static readonly IReadOnlyList<string> ProxyNames = new[]
    {
        "dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "wininet.dll", "winhttp.dll", "d3d12.dll",
    };

    private const int ReadLimit = 256 * 1024;
    private const int MaxScalerLines = 512;
    private const string ScalerManifest = "HelixSR-Scaler.files";
    private const string ScalerHeader = "# HelixSR Scaler, installed by HelixSR Desktop";
    private const string InstallRecord = "helixsr-install.json";

    private static readonly string[] HelixLogs =
    {
        "OptiScaler.log", "helixsr.log", "HLX_FSR.log", "HelixSR-fsrfg/helixsr.log", "_storage_/HLX_FSR.log",
    };

    private static readonly Regex HelixDlss = new(@"FFX upscaler:[\s\x1c-\x1f]*HLX DLSS\b", RegexOptions.CultureInvariant);

    public static ForeignIdentity Read(IReadOnlyFileSystem fileSystem, string target)
    {
        var evidence = new List<string>();
        var variants = new HashSet<string>(StringComparer.Ordinal);
        var manifestError = false;
        var record = FileSystemPath.Join(target, InstallRecord);
        var helix = fileSystem.Exists(record) || fileSystem.IsSymbolicLink(record);
        if (helix)
        {
            evidence.Add(InstallRecord);
            manifestError = !IsValidRecord(JsonTree.Parse(Text(fileSystem, target, InstallRecord) ?? string.Empty));
        }

        var scaler = FileSystemPath.Join(target, ScalerManifest);
        if (fileSystem.Exists(scaler) || fileSystem.IsSymbolicLink(scaler))
        {
            helix = true;
            evidence.Add(ScalerManifest);
            var variant = ScalerVariant(fileSystem, target);
            manifestError = manifestError || variant is null;
            if (variant is not null)
            {
                variants.Add(variant);
            }
        }

        foreach (var name in HelixLogs)
        {
            var content = Text(fileSystem, target, name);
            if (content is null)
            {
                continue;
            }

            if (HelixDlss.IsMatch(content))
            {
                helix = true;
                variants.Add("dlss");
                evidence.Add(name + ":HLX DLSS");
            }

            if (content.Contains("HLX-FSR-4 own runtime active:"))
            {
                helix = true;
                variants.Add("fsr");
                evidence.Add(name + ":HLX FSR 4");
            }
        }

        if (helix)
        {
            var variant = variants.Count == 1 && !manifestError ? variants.First() : "unknown";
            return new ForeignIdentity("helixsr", variant, evidence, manifestError);
        }

        foreach (var name in new[] { "OptiScaler.ini", "OptiScaler.log" })
        {
            if (Text(fileSystem, target, name) is not null)
            {
                evidence.Add(name);
            }
        }

        return new ForeignIdentity(evidence.Count > 0 ? "optiscaler" : "unknown", "unknown", evidence, false);
    }

    private static bool IsValidRecord(System.Xml.Linq.XElement? record)
    {
        if (record is null || !JsonTree.IsObject(record))
        {
            return false;
        }

        var files = JsonTree.Member(record, "files");
        return files is null || (JsonTree.IsArray(files) && files.Elements().All(JsonTree.IsString));
    }

    /// <summary>"dlss" for a complete HelixSR Scaler install in the NGX layout, or null when its manifest cannot be trusted.</summary>
    private static string? ScalerVariant(IReadOnlyFileSystem fileSystem, string target)
    {
        var text = Text(fileSystem, target, ScalerManifest);
        if (text is null)
        {
            return null;
        }

        var lines = PythonText.SplitLines(text);
        if (lines.Count > MaxScalerLines || lines.Count == 0 || PythonText.Strip(lines[0]) != ScalerHeader)
        {
            return null;
        }

        var layouts = lines.Where(line => line.StartsWith("# layout=", StringComparison.Ordinal))
            .Select(line => PythonText.Strip(line.Substring("# layout=".Length))).ToArray();
        var names = lines.Where(line => line.StartsWith("name=", StringComparison.Ordinal))
            .Select(line => PythonText.Strip(line.Substring("name=".Length))).ToArray();
        var files = lines
            .Where(line => PythonText.Strip(line).Length > 0 && !line.StartsWith("#", StringComparison.Ordinal)
                && !line.StartsWith("name=", StringComparison.Ordinal))
            .Select(PythonText.Strip)
            .ToArray();
        if (layouts.Length != 1 || names.Length != 1 || !ProxyNames.Contains(names[0])
            || files.Length != files.Distinct(StringComparer.Ordinal).Count())
        {
            return null;
        }

        foreach (var name in files)
        {
            if (name.StartsWith("/", StringComparison.Ordinal) || name.Split('/').Contains("..") || name.IndexOfAny(new[] { '\\', ':', '\0' }) >= 0
                || name != NormalPosix(name) || SelfAndParents(name).Any(part => fileSystem.IsSymbolicLink(FileSystemPath.Join(target, part))))
            {
                return null;
            }
        }

        if (layouts[0] != "ngx")
        {
            return null;
        }

        var required = new[] { names[0], "OptiScaler.ini", "HelixSR/helixsr.dll" };
        if (!required.All(name => files.Contains(name) && fileSystem.IsFile(FileSystemPath.Join(target, name))))
        {
            return null;
        }

        var config = Text(fileSystem, target, "OptiScaler.ini");
        if (config is null || !config.Contains("HelixSR Scaler") || !config.Contains("[HelixSR]"))
        {
            return null;
        }

        foreach (var name in new[] { names[0], "HelixSR/helixsr.dll" })
        {
            var path = FileSystemPath.Join(target, name);
            if (fileSystem.IsSymbolicLink(path))
            {
                return null;
            }

            var head = FileSystemPath.ReadAtMost(fileSystem, path, 2);
            if (head is null || head.Length != 2 || head[0] != 'M' || head[1] != 'Z')
            {
                return null;
            }
        }

        return "dlss";
    }

    /// <summary>A small text file another tool left, never followed through a link and never larger than the limit.</summary>
    private static string? Text(IReadOnlyFileSystem fileSystem, string target, string name)
    {
        if (fileSystem.IsSymbolicLink(target)
            || SelfAndParents(name).Skip(1).Any(parent => fileSystem.IsSymbolicLink(FileSystemPath.Join(target, parent))))
        {
            return null;
        }

        var path = FileSystemPath.Join(target, name);
        if (fileSystem.IsSymbolicLink(path) || !fileSystem.IsFile(path))
        {
            return null;
        }

        var data = FileSystemPath.ReadAtMost(fileSystem, path, ReadLimit + 1);
        if (data is null || data.Length > ReadLimit)
        {
            return null;
        }

        try
        {
            return new UTF8Encoding(false, true).GetString(data);
        }
        catch (DecoderFallbackException)
        {
            return null;
        }
    }

    /// <summary>The relative path and each folder above it, outermost last; the game folder itself is left out.</summary>
    private static IEnumerable<string> SelfAndParents(string relative)
    {
        var parts = relative.Split('/').Where(part => part.Length > 0 && part != ".").ToArray();
        for (var count = parts.Length; count > 0; count--)
        {
            yield return string.Join("/", parts, 0, count);
        }
    }

    private static string NormalPosix(string relative)
    {
        var parts = relative.Split('/').Where(part => part.Length > 0 && part != ".").ToArray();
        return parts.Length == 0 ? "." : string.Join("/", parts);
    }
}
