namespace PanelDeControl.Core.Upscalers;

/// <summary>What a build is called in a list or on a cover, as <c>badgeLabel</c> does on Linux.</summary>
public static class UpscalerLabel
{
    public static string Badge(string family, string version, IReadOnlyCollection<string> models, string? model)
    {
        if (family == "proton")
        {
            return version;
        }

        var name = family switch
        {
            "xess" => "XeSS",
            "helixsr" => "HLX",
            _ => "FSR",
        };
        var lite = models.Contains("lite") && model != "full" ? " Lite" : string.Empty;
        return $"{name} {version}{lite}".Trim();
    }

    public static string? Badge(UpscalerBuild? build, string? model) =>
        build is null ? null : Badge(build.Family, build.Version, build.Models.Select(entry => entry.Id).ToArray(), model);
}
