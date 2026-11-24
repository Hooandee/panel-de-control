using System.Globalization;
using Microsoft.Win32;
using PanelDeControl.Core.Upscalers;

namespace PanelDeControl.Hardware.Upscalers;

public interface IVcRuntimeProbe
{
    /// <summary>Installed Visual C++ 2015-2022 x64 runtime version, or null when absent or unreadable. Never throws.</summary>
    string? InstalledVersion();
}

public sealed class VcRuntimeProbe : IVcRuntimeProbe
{
    internal const string RuntimeKey = @"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64";
    internal const string RuntimeKeyWow64 = @"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64";

    private readonly Func<string, IReadOnlyDictionary<string, object?>?> _readKey;

    public VcRuntimeProbe() : this(ReadRegistryKey)
    {
    }

    internal VcRuntimeProbe(Func<string, IReadOnlyDictionary<string, object?>?> readKey)
    {
        _readKey = readKey;
    }

    public string? InstalledVersion()
    {
        string? best = null;
        foreach (var path in new[] { RuntimeKey, RuntimeKeyWow64 })
        {
            string? version;
            try
            {
                version = VersionOf(_readKey(path));
            }
            catch (Exception)
            {
                continue;
            }
            if (version is not null && (best is null || WindowsRedistStatus.Compare(version, best) > 0))
            {
                best = version;
            }
        }
        return best;
    }

    private static string? VersionOf(IReadOnlyDictionary<string, object?>? values)
    {
        if (values is null || !values.TryGetValue("Installed", out var installed) || Number(installed) != 1)
        {
            return null;
        }
        if (values.TryGetValue("Version", out var text) && text is string { Length: > 0 } version)
        {
            var trimmed = version.Trim().TrimStart('v', 'V');
            if (trimmed.Length > 0 && trimmed.Split('.').All(part => part.Length > 0 && part.All(char.IsDigit)))
            {
                return trimmed;
            }
        }
        var parts = new[] { "Major", "Minor", "Bld", "Rbld" }.Select(name => values.TryGetValue(name, out var value) ? Number(value) : null).ToArray();
        return parts[0] is null || parts[1] is null
            ? null
            : string.Join(".", parts.Select(part => (part ?? 0).ToString(CultureInfo.InvariantCulture)));
    }

    private static long? Number(object? value) => value switch
    {
        int number => number,
        uint number => number,
        long number => number,
        _ => null,
    };

    private static IReadOnlyDictionary<string, object?>? ReadRegistryKey(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            return null;
        }
        using var root = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
        using var key = root.OpenSubKey(path);
        if (key is null)
        {
            return null;
        }
        var values = new Dictionary<string, object?>(StringComparer.Ordinal);
        foreach (var name in key.GetValueNames())
        {
            values[name] = key.GetValue(name);
        }
        return values;
    }
}
