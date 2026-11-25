using System.Globalization;

namespace PanelDeControl.Core.Upscalers;

public enum RedistState
{
    Satisfied,
    Missing,
    Outdated,
}

public sealed class RedistStatus
{
    public RedistStatus(RedistState state, string? installedVersion, string requiredVersion)
    {
        State = state;
        InstalledVersion = installedVersion;
        RequiredVersion = requiredVersion;
    }

    public RedistState State { get; }

    public string? InstalledVersion { get; }

    public string RequiredVersion { get; }
}

public static class WindowsRedistStatus
{
    /// <summary>
    /// Whether the installed runtime meets the dependency's minimum version, compared number by number
    /// (14.9 is older than 14.40). An absent or unreadable installed version counts as missing.
    /// </summary>
    public static RedistStatus Evaluate(RecipeDependency dependency, string? installedVersion)
    {
        var required = dependency.Version ?? "0";
        var installed = Parse(installedVersion);
        if (installed is null)
        {
            return new RedistStatus(RedistState.Missing, null, required);
        }
        var minimum = Parse(required) ?? new[] { 0L };
        return new RedistStatus(Compare(installed, minimum) >= 0 ? RedistState.Satisfied : RedistState.Outdated, installedVersion!.Trim(), required);
    }

    public static int Compare(string left, string right) =>
        Compare(Parse(left) ?? Array.Empty<long>(), Parse(right) ?? Array.Empty<long>());

    private static int Compare(long[] left, long[] right)
    {
        for (var index = 0; index < Math.Max(left.Length, right.Length); index++)
        {
            var order = (index < left.Length ? left[index] : 0).CompareTo(index < right.Length ? right[index] : 0);
            if (order != 0)
            {
                return order;
            }
        }
        return 0;
    }

    private static long[]? Parse(string? version)
    {
        if (string.IsNullOrWhiteSpace(version))
        {
            return null;
        }
        var text = version!.Trim();
        if (text.StartsWith("v", StringComparison.OrdinalIgnoreCase))
        {
            text = text.Substring(1);
        }
        var parts = text.Split('.');
        var numbers = new long[parts.Length];
        for (var index = 0; index < parts.Length; index++)
        {
            if (!long.TryParse(parts[index], NumberStyles.None, CultureInfo.InvariantCulture, out numbers[index]))
            {
                return null;
            }
        }
        return numbers;
    }
}
