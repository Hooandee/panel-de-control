using System.Text.RegularExpressions;

namespace PanelDeControl.Hardware.Themes;

public sealed record SteamTarget(string Id, string Title, string Url, IReadOnlySet<string> DocumentClasses);

/// <summary>
/// Resolves CSS Loader target names (the values of <c>inject</c>) against Steam's CEF pages,
/// with the same aliases CSS Loader ships so existing themes keep their meaning.
/// </summary>
public static class ThemeTargetMatcher
{
    private const int MaximumAliasDepth = 8;

    private static readonly IReadOnlyDictionary<string, string[]> Aliases = new Dictionary<string, string[]>(StringComparer.Ordinal)
    {
        ["desktop"] = new[] { "Steam|SteamLibraryWindow" },
        ["desktopchat"] = new[] { "!friendsui-container" },
        ["desktoppopup"] = new[] { "OverlayBrowser_Browser", "SP Overlay:.*", "notificationtoasts_.*", "SteamBrowser_Find", @"OverlayTab\d+_Find", "!ModalDialogPopup", "!FullModalOverlay" },
        ["desktopoverlay"] = new[] { "desktoppopup" },
        ["desktopcontextmenu"] = new[] { ".*Menu", ".*Supernav" },
        ["bigpicture"] = new[] { "~Valve Steam Gamepad/default~", "~Valve%20Steam%20Gamepad~" },
        ["bigpictureoverlay"] = new[] { "QuickAccess", "MainMenu" },
        ["store"] = new[] { "~https://store.steampowered.com~", "~https://steamcommunity.com~" },
        ["SP"] = new[] { "bigpicture" },
        ["Steam Big Picture Mode"] = new[] { "bigpicture" },
        ["MainMenu"] = new[] { "MainMenu.*" },
        ["MainMenu_.*"] = new[] { "MainMenu" },
        ["QuickAccess"] = new[] { "QuickAccess.*" },
        ["QuickAccess_.*"] = new[] { "QuickAccess" },
        ["Steam"] = new[] { "desktop" },
        ["SteamLibraryWindow"] = new[] { "desktop" },
        ["All"] = new[] { "bigpicture", "bigpictureoverlay" },
    };

    public static bool Matches(SteamTarget target, string selector) =>
        Expand(selector, MaximumAliasDepth).Any(pattern => MatchesPattern(target, pattern));

    public static bool IsBigPicture(SteamTarget target) => Matches(target, "bigpicture");

    private static IEnumerable<string> Expand(string selector, int depth)
    {
        if (depth == 0 || !Aliases.TryGetValue(selector, out var expansions))
        {
            yield return selector;
            yield break;
        }

        foreach (var expansion in expansions)
        {
            if (expansion == selector)
            {
                yield return expansion;
                continue;
            }

            foreach (var pattern in Expand(expansion, depth - 1))
            {
                yield return pattern;
            }
        }
    }

    private static bool MatchesPattern(SteamTarget target, string pattern)
    {
        if (pattern.Length > 2 && pattern.StartsWith('~') && pattern.EndsWith('~'))
        {
            return target.Url.Contains(pattern[1..^1], StringComparison.Ordinal);
        }

        if (pattern.StartsWith('!'))
        {
            return target.DocumentClasses.Contains(pattern[1..]);
        }

        try
        {
            return Regex.IsMatch(target.Title, $"^(?:{pattern})$", RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(50));
        }
        catch (Exception exception) when (exception is ArgumentException or RegexMatchTimeoutException)
        {
            return false;
        }
    }
}
