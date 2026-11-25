namespace PanelDeControl.Core.Upscalers;

/// <summary>Changing an OptiScaler install in place, as the Linux backend's <c>configure</c> and <c>set_ini</c> do.</summary>
public static class UpscalerSettings
{
    public const int MaximumIniValueLength = 200;

    private static readonly string[] QualityModes = { "DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance" };

    /// <summary>Keys Panel writes itself, so the editor never lets the user take them over (<c>_managed_keys</c>).</summary>
    public static ISet<string> ManagedKeys(BuildCatalog catalog, InstalledUpscaler install)
    {
        var keys = new HashSet<string>(catalog.BaseIni.Keys, StringComparer.Ordinal)
        {
            "QualityOverrides.QualityRatioOverrideEnabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness",
            "FrameGen.Enabled", "FrameGen.FGInput", "FrameGen.FGOutput", "OptiFG.HUDFix",
        };
        foreach (var mode in QualityModes)
        {
            keys.Add("QualityOverrides.QualityRatio" + mode);
        }
        keys.UnionWith(install.Managed);
        if (catalog.Build(install.Build) is { } build)
        {
            keys.UnionWith(build.Ini.Keys);
            foreach (var model in build.Models)
            {
                keys.UnionWith(model.Ini.Keys);
            }
        }
        return keys;
    }

    /// <summary>The sharpness the image controls left in the INI, kept over the quality picker's own (<c>_image_overrides</c>).</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> ImageOverrides(InstalledUpscaler install, string text)
    {
        if (install.ImageOverrides.Count == 0)
        {
            return Array.Empty<KeyValuePair<string, string>>();
        }
        var result = new List<KeyValuePair<string, string>>();
        foreach (var key in ImageSettings.ManagedSharpnessKeys)
        {
            if (IniText.Read(text, key) is { } value)
            {
                result.Add(new KeyValuePair<string, string>(key, value));
            }
        }
        return result;
    }

    /// <summary>What a new choice writes over an installed INI: quality and sharpness, model, frame generation, then the image controls' sharpness.</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> ConfigureOverrides(BuildCatalog catalog, InstalledUpscaler install, UpscalerChoice choice,
        FrameGenPlan? frameGen, string text)
    {
        var build = catalog.Build(install.Build);
        return Merge(
            PanelIni.OptionOverrides(catalog, choice, reset: true),
            UpscalerPlanner.ModelOverrides(build, choice.Model),
            UpscalerPlanner.FrameGenOverrides(frameGen, choice.FrameGen, install.Anr),
            ImageOverrides(install, text));
    }

    /// <summary>While the game runs only quality and sharpness change, saved for its next start (<c>_configure_running</c>).</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> RunningOverrides(BuildCatalog catalog, InstalledUpscaler install, UpscalerChoice choice, string text) =>
        Merge(PanelIni.OptionOverrides(catalog, choice, reset: true), ImageOverrides(install, text));

    /// <summary>Only turning frame generation off, so nothing else is re-planned (<c>only_disable</c>).</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> FrameGenOff(InstalledUpscaler install) =>
        UpscalerPlanner.FrameGenOverrides(null, false, install.Anr).ToList();

    /// <summary>The user's hand edits that survive a reinstall: never one of Panel's own keys.</summary>
    public static IReadOnlyList<KeyValuePair<string, string>> CarriedEdits(IReadOnlyList<KeyValuePair<string, string>> edited, IEnumerable<string> panel)
    {
        var owned = new HashSet<string>(panel, StringComparer.Ordinal);
        return edited.Where(pair => !owned.Contains(pair.Key)).ToList();
    }

    /// <summary>
    /// Checks one hand edit against the installed INI (<c>_set_ini</c>): the key must exist and not be Panel's, and a key
    /// with a closed set of values only takes one of them. A bare <c>Key</c> resolves when the INI has exactly one.
    /// </summary>
    public static KeyValuePair<string, string> ValidateEdit(string text, string dotted, string value, ISet<string> managed)
    {
        value = value.Trim();
        if (value.Length == 0 || value.Length > MaximumIniValueLength || value.IndexOfAny(new[] { '\r', '\n', '[', ']' }) >= 0)
        {
            throw new UpscalerException("ini_value");
        }
        var schema = IniText.Schema(text);
        if (!dotted.Contains('.') && ResolveSettings(schema, new[] { new KeyValuePair<string, string>(dotted, value) }).FirstOrDefault() is { Key: not null } resolved)
        {
            dotted = resolved.Key;
        }
        var dot = dotted.IndexOf('.');
        var sectionName = dot < 0 ? dotted : dotted.Substring(0, dot);
        var keyName = dot < 0 ? "" : dotted.Substring(dot + 1);
        var entry = schema.Where(section => section.Name == sectionName).SelectMany(section => section.Keys).FirstOrDefault(key => key.Key == keyName);
        if (entry is null)
        {
            throw new UpscalerException("ini_key");
        }
        if (managed.Contains(dotted))
        {
            throw new UpscalerException("ini_managed");
        }
        if (entry.Choices is not null && !entry.Choices.Contains(value))
        {
            throw new UpscalerException("ini_value");
        }
        return new KeyValuePair<string, string>(dotted, value);
    }

    /// <summary>
    /// Bare <c>Key=value</c> pairs (as the OptiScaler wiki writes them) mapped to <c>Section.Key</c>, only when the INI has
    /// exactly one such key and the value is one it accepts (<c>wiki.resolve_settings</c>).
    /// </summary>
    public static IReadOnlyList<KeyValuePair<string, string>> ResolveSettings(IReadOnlyList<IniSchemaSection> schema, IEnumerable<KeyValuePair<string, string>> settings)
    {
        var resolved = new List<KeyValuePair<string, string>>();
        foreach (var setting in settings)
        {
            var found = schema.SelectMany(section => section.Keys.Where(key => key.Key.ToLowerInvariant() == setting.Key.ToLowerInvariant()).Select(key => (Section: section.Name, Entry: key))).ToList();
            if (found.Count != 1)
            {
                continue;
            }
            var (section, entry) = found[0];
            if (entry.Choices is { Count: > 0 } choices && !choices.Any(choice => choice.ToLowerInvariant() == setting.Value.ToLowerInvariant()))
            {
                continue;
            }
            if (entry.Choices is not { Count: > 0 } && !WikiValue.IsMatch(setting.Value))
            {
                continue;
            }
            var dotted = section + "." + entry.Key;
            var index = resolved.FindIndex(pair => pair.Key == dotted);
            if (index >= 0)
            {
                resolved[index] = new KeyValuePair<string, string>(dotted, setting.Value);
            }
            else
            {
                resolved.Add(new KeyValuePair<string, string>(dotted, setting.Value));
            }
        }
        return resolved;
    }

    private static readonly System.Text.RegularExpressions.Regex WikiValue = new(@"^(?:-?\d+(?:\.\d+)?|0x[0-9a-fA-F]+|true|false|auto)\z",
        System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant);

    /// <summary>Python's dict merge over several mappings: a key keeps its first position and takes the last value.</summary>
    private static IReadOnlyList<KeyValuePair<string, string>> Merge(params IEnumerable<KeyValuePair<string, string>>[] parts)
    {
        var result = new List<KeyValuePair<string, string>>();
        foreach (var part in parts)
        {
            foreach (var pair in part)
            {
                var index = result.FindIndex(item => item.Key == pair.Key);
                if (index >= 0)
                {
                    result[index] = pair;
                }
                else
                {
                    result.Add(pair);
                }
            }
        }
        return result;
    }
}
