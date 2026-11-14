using System.Globalization;

namespace PanelDeControl.Core.Upscalers;

/// <summary>What the user picked for a game; anything unknown is dropped, as the Linux backend does.</summary>
public sealed class UpscalerChoice
{
    public string? Quality { get; set; }

    public string? Sharpness { get; set; }

    public bool FrameGen { get; set; }

    public string? FrameGenRoute { get; set; }

    public string? Model { get; set; }
}

/// <summary>The OptiScaler.ini keys Panel owns for an install, in the order they are written (<c>panel_ini</c>).</summary>
public static class PanelIni
{
    private static readonly string[] QualityModes = { "DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance" };

    public static IReadOnlyList<KeyValuePair<string, string>> Compute(BuildCatalog catalog, UpscalerBuild build,
        IReadOnlyDictionary<string, string>? recipeIni, bool optiPatcher, UpscalerChoice choice, FrameGenPlan? frameGenPlan)
    {
        var values = new OrderedValues();
        values.SetAll(catalog.BaseIni);
        values.SetAll(build.Ini);
        if (recipeIni is not null)
        {
            values.SetAll(recipeIni);
        }
        values.SetAll(OptionOverrides(catalog, choice));
        if (optiPatcher)
        {
            values.Set("Plugins.LoadAsiPlugins", "true");
        }
        values.SetAll(UpscalerPlanner.ModelOverrides(build, choice.Model));
        values.SetAll(UpscalerPlanner.FrameGenOverrides(frameGenPlan, choice.FrameGen));
        return values.Pairs;
    }

    public static IReadOnlyList<KeyValuePair<string, string>> OptionOverrides(BuildCatalog catalog, UpscalerChoice choice, bool reset = false)
    {
        var values = new OrderedValues();
        if (choice.Quality is not null && catalog.QualityRatios.TryGetValue(choice.Quality, out var ratio))
        {
            values.Set("QualityOverrides.QualityRatioOverrideEnabled", "true");
            // DLAA is the game's native-AA mode: without it the chosen quality never applies there.
            foreach (var mode in QualityModes)
            {
                values.Set("QualityOverrides.QualityRatio" + mode, ratio.ToString("0.00", CultureInfo.InvariantCulture));
            }
        }
        else
        {
            values.Set("QualityOverrides.QualityRatioOverrideEnabled", "false");
        }
        var known = choice.Sharpness is not null && catalog.Sharpness.ContainsKey(choice.Sharpness);
        if (known && catalog.Sharpness[choice.Sharpness!] is { } sharpness)
        {
            values.Set("Sharpness.OverrideSharpness", "true");
            values.Set("Sharpness.Sharpness", sharpness.ToString("0.00", CultureInfo.InvariantCulture));
        }
        else if (reset || (known && choice.Sharpness == "off"))
        {
            values.Set("Sharpness.OverrideSharpness", "false");
        }
        return values.Pairs;
    }

    /// <summary>Python's dict merge: a key keeps its first position and takes the last value.</summary>
    private sealed class OrderedValues
    {
        private readonly List<KeyValuePair<string, string>> _pairs = new();

        public IReadOnlyList<KeyValuePair<string, string>> Pairs => _pairs;

        public void Set(string key, string value)
        {
            var index = _pairs.FindIndex(pair => pair.Key == key);
            if (index >= 0)
            {
                _pairs[index] = new KeyValuePair<string, string>(key, value);
            }
            else
            {
                _pairs.Add(new KeyValuePair<string, string>(key, value));
            }
        }

        public void SetAll(IEnumerable<KeyValuePair<string, string>> values)
        {
            foreach (var pair in values)
            {
                Set(pair.Key, pair.Value);
            }
        }
    }
}
