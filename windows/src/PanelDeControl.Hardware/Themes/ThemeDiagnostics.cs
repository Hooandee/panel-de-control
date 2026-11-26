using System.Text.Json.Nodes;

namespace PanelDeControl.Hardware.Themes;

public sealed record ThemeTargetDiagnostics(string Type, string Title, string Url, bool BigPicture, int? SheetsExpected, int? SheetsApplied);

/// <summary>What one engine cycle saw: enough to tell a missing target from a CSS write that never reached a visible document.</summary>
public sealed record ThemeDiagnostics(
    DateTimeOffset At,
    string Connection,
    IReadOnlyList<ThemeTargetDiagnostics> Targets,
    ThemeHostStatus Host,
    IReadOnlyDictionary<string, ThemeApplication> Themes,
    int? LiveClasses,
    ClassTableInfo? ClassTable,
    string? LastError)
{
    private const int MaximumUrlLength = 200;

    /// <summary>Scheme, host and path only: DevTools URLs carry user-agent strings and tokens in their query.</summary>
    public static string SanitizeUrl(string url)
    {
        var end = url.IndexOfAny(new[] { '?', '#' });
        var kept = end >= 0 ? url.Substring(0, end) : url;
        return kept.Length > MaximumUrlLength ? kept.Substring(0, MaximumUrlLength) : kept;
    }

    /// <summary>
    /// Steam's own UI keeps its title and path. Any other target is a web page (a profile
    /// carries the SteamID64, a chat the friend's name), so it keeps scheme and host only.
    /// </summary>
    private static (string? Title, string? Url) Private(ThemeTargetDiagnostics target)
    {
        if (target.BigPicture
            || target.Title == SteamThemeEngine.SharedContextTitle
            || target.Url.StartsWith("about:", StringComparison.OrdinalIgnoreCase))
        {
            return (target.Title, target.Url);
        }

        if (!Uri.TryCreate(target.Url, UriKind.Absolute, out var uri))
        {
            return (null, null);
        }

        return string.Equals(uri.Host, "steamloopback.host", StringComparison.OrdinalIgnoreCase)
            ? (target.Title, target.Url)
            : (null, $"{uri.Scheme}://{uri.Host}");
    }

    public JsonObject ToJson()
    {
        var themes = new JsonArray();
        foreach (var (name, application) in Themes.OrderBy(pair => pair.Key, StringComparer.Ordinal))
        {
            themes.Add(new JsonObject
            {
                ["name"] = name,
                ["pages_expected"] = application.PagesExpected,
                ["pages_applied"] = application.PagesApplied,
                ["runtime_expected"] = application.RuntimeExpected,
                ["runtime_mounted"] = application.RuntimeMounted,
            });
        }

        var targets = new JsonArray();
        foreach (var target in Targets)
        {
            var (title, url) = Private(target);
            targets.Add(new JsonObject
            {
                ["type"] = target.Type,
                ["title"] = title,
                ["url"] = url,
                ["big_picture"] = target.BigPicture,
                ["sheets_expected"] = target.SheetsExpected,
                ["sheets_applied"] = target.SheetsApplied,
            });
        }

        var errors = new JsonArray();
        foreach (var error in Host.Errors)
        {
            errors.Add(error);
        }

        var mounted = new JsonArray();
        foreach (var extension in Host.Mounted)
        {
            mounted.Add(extension);
        }

        var document = Host.Document;
        return new JsonObject
        {
            ["at"] = At.ToString("O", System.Globalization.CultureInfo.InvariantCulture),
            ["connection"] = Connection,
            ["last_error"] = LastError,
            ["themes"] = themes,
            ["targets"] = targets,
            ["host"] = new JsonObject
            {
                ["present"] = Host.Present,
                ["steam_document"] = Host.SteamDocument,
                ["mounted"] = mounted,
                ["errors"] = errors,
                ["game_running"] = Host.GameRunning,
                ["document"] = document is null
                    ? null
                    : new JsonObject
                    {
                        ["title"] = document.Title,
                        ["location"] = document.Location,
                        ["visibility_state"] = document.VisibilityState,
                        ["inner_width"] = document.InnerWidth,
                        ["inner_height"] = document.InnerHeight,
                    },
            },
            ["live_classes"] = LiveClasses,
            ["class_table"] = ClassTable is null
                ? null
                : new JsonObject { ["rows"] = ClassTable.Rows, ["age_hours"] = ClassTable.AgeHours },
        };
    }

    /// <summary>The report section: the latest cycle and the newest one that ran with a theme enabled.</summary>
    public static JsonObject Report(ThemeDiagnostics? current, ThemeDiagnostics? lastWhileEnabled) => new()
    {
        ["current"] = current?.ToJson(),
        ["last_while_enabled"] = lastWhileEnabled?.ToJson(),
    };
}
