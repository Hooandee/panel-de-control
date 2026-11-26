using System;
using System.Linq;
using PanelDeControl.Core.Upscalers;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

/// <summary>What the user has to bring before the recipe is complete: files Panel cannot download and a missing runtime.</summary>
public sealed partial class UpscalersView
{
    private readonly StackPanel needsPanel = new() { Spacing = 6, Visibility = Visibility.Collapsed };

    private UIElement BuildNeedsPanel() => needsPanel;

    private void RenderNeeds()
    {
        needsPanel.Children.Clear();
        var dependencies = detail?.Recipe?.Dependencies ?? Array.Empty<UpscalerDependencyStatus>();
        foreach (var dependency in dependencies)
        {
            var name = dependency.Name ?? dependency.Id;
            string? text = dependency switch
            {
                { State: "user_file", UserState: "missing" or null } => string.Format(Localized("UpscalersNeedUserFile"), name, dependency.Required ?? "—"),
                { State: "user_file", UserState: "avoid" } => string.Format(Localized("UpscalersNeedUserFileAvoid"), name, dependency.Required ?? "—"),
                { State: "user_file", UserState: "other_version" } => string.Format(Localized("UpscalersNeedUserFileOther"), name, dependency.Required ?? "—"),
                { State: "missing" } => string.Format(Localized("UpscalersNeedRuntime"), name),
                { State: "outdated" } => string.Format(Localized("UpscalersNeedRuntimeOutdated"), name, dependency.Required ?? "—"),
                _ => null,
            };
            if (text is null)
            {
                continue;
            }

            var line = new TextBlock
            {
                Text = text,
                Style = Resource<Style>("PdcCaptionStyle"),
                TextWrapping = TextWrapping.WrapWholeWords,
                Foreground = Resource<Brush>("PdcWarnBrush"),
            };
            needsPanel.Children.Add(line);
            if (dependency.Url is { } url && Uri.TryCreate(url, UriKind.Absolute, out var page) && page.Scheme == Uri.UriSchemeHttps)
            {
                var open = new Button { Tag = page };
                Prepare(open, "UpscalersNeedOpen", async (sender, _) => await Windows.System.Launcher.LaunchUriAsync((Uri)((Button)sender).Tag));
                needsPanel.Children.Add(open);
            }
        }

        needsPanel.Visibility = needsPanel.Children.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
    }
}
