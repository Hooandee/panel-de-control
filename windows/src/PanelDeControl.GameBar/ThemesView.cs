using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using PanelDeControl.Core.Themes;
using Windows.ApplicationModel.Resources;
using Windows.ApplicationModel.Resources.Core;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

/// <summary>
/// Temas on Windows: the official catalog, install and update, on/off and every option of the
/// theme, with the state Steam reads back.
/// </summary>
public sealed class ThemesView : UserControl
{
    private static readonly ResourceLoader Strings = ResourceLoader.GetForViewIndependentUse();

    private readonly ThemesClient client = new();
    private readonly StackPanel root = new() { Spacing = 10 };
    private readonly TextBlock connectionTitle = new();
    private readonly TextBlock connectionDetail = new();
    private readonly Button connectionAction = new();
    private readonly Border connectionCard;
    private readonly StackPanel themeList = new() { Spacing = 10 };
    private readonly TextBlock emptyText = new();
    private readonly Dictionary<string, ThemeCard> cards = new(StringComparer.Ordinal);
    private readonly HashSet<string> expanded = new(StringComparer.Ordinal);
    private readonly string language;
    private string structure = string.Empty;
    private bool operationPending;
    private bool refreshing;
    private bool applying;
    private ThemesResponse? last;

    public ThemesView()
    {
        language = UiLanguage();
        connectionTitle.Style = Resource<Style>("PdcTitleStyle");
        connectionDetail.Style = Resource<Style>("PdcMutedStyle");
        connectionDetail.Margin = new Thickness(0, 4, 0, 0);
        connectionDetail.TextWrapping = TextWrapping.WrapWholeWords;
        connectionAction.Style = Resource<Style>("PdcChipButtonStyle");
        connectionAction.Margin = new Thickness(0, 12, 0, 0);
        connectionAction.Padding = new Thickness(14, 9, 14, 9);
        connectionAction.Click += ConnectionAction_Click;
        connectionCard = new Border
        {
            Style = Resource<Style>("PdcCardStyle"),
            Child = new StackPanel { Children = { connectionTitle, connectionDetail, connectionAction } },
        };
        emptyText.Style = Resource<Style>("PdcMutedStyle");
        emptyText.TextWrapping = TextWrapping.WrapWholeWords;
        root.Children.Add(connectionCard);
        root.Children.Add(themeList);
        root.Children.Add(emptyText);
        Content = root;
    }

    public async Task RefreshAsync()
    {
        if (refreshing || operationPending)
        {
            return;
        }

        refreshing = true;
        try
        {
            var response = await client.GetAsync();
            if (!operationPending)
            {
                Apply(response, null);
            }
        }
        finally
        {
            refreshing = false;
        }
    }

    private void Apply(ThemesResponse response, string? operationError)
    {
        applying = true;
        try
        {
            last = response;
            ApplyConnection(response, operationError);
            var installed = response.Themes.Where(theme => theme.Installed || theme.PublishedVersion is not null).ToArray();
            var signature = string.Join("|", installed.Select(theme =>
                $"{theme.Name}:{theme.InstalledVersion}:{theme.PublishedVersion}:{theme.Broken}:{string.Join(",", (theme.Options ?? new ThemeOption[0]).Select(option => option.Name + "=" + option.Values.Length))}"));
            if (signature != structure)
            {
                structure = signature;
                themeList.Children.Clear();
                cards.Clear();
                foreach (var theme in installed)
                {
                    var card = BuildCard(theme);
                    cards[theme.Name] = card;
                    themeList.Children.Add(card.Root);
                }
            }

            foreach (var theme in installed)
            {
                UpdateCard(cards[theme.Name], theme);
            }

            emptyText.Text = installed.Length == 0
                ? response.CatalogError is null ? Localized("ThemesCatalogLoading") : Localized("ThemesCatalogUnavailable")
                : string.Empty;
            emptyText.Visibility = installed.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        }
        finally
        {
            applying = false;
        }
    }

    private void ApplyConnection(ThemesResponse response, string? operationError)
    {
        string title;
        string detail;
        string? action = null;
        if (response.Status == ThemesResponseStatus.Fault && response.ErrorCode?.StartsWith("themes_broker", StringComparison.Ordinal) == true)
        {
            title = Localized("ThemesCompanionTitle");
            detail = Localized("ThemesCompanionDetail");
        }
        else
        {
            switch (response.Connection)
            {
                case ThemesConnection.SteamNotInstalled:
                    title = Localized("ThemesSteamMissingTitle");
                    detail = Localized("ThemesSteamMissingDetail");
                    break;
                case ThemesConnection.DebuggingOff:
                case ThemesConnection.RestartRequired:
                    title = Localized("ThemesRestartTitle");
                    detail = Localized("ThemesRestartDetail");
                    action = Localized("ThemesRestartAction");
                    break;
                case ThemesConnection.SteamNotRunning:
                    title = Localized("ThemesSteamClosedTitle");
                    detail = Localized("ThemesSteamClosedDetail");
                    break;
                case ThemesConnection.WaitingForBigPicture:
                    title = Localized("ThemesWaitingTitle");
                    detail = Localized("ThemesWaitingDetail");
                    break;
                default:
                    title = Localized("ThemesConnectedTitle");
                    detail = Localized("ThemesConnectedDetail");
                    break;
            }
        }

        if (operationError is not null)
        {
            detail = string.Format(Localized("ThemesOperationFailed"), operationError);
        }

        connectionTitle.Text = title;
        connectionDetail.Text = detail;
        connectionAction.Content = action;
        connectionAction.Visibility = action is null ? Visibility.Collapsed : Visibility.Visible;
        connectionAction.IsEnabled = !operationPending;
    }

    private ThemeCard BuildCard(ThemeEntry theme)
    {
        var card = new ThemeCard(theme.Name);
        card.Title.Style = Resource<Style>("PdcTitleStyle");
        card.Description.Style = Resource<Style>("PdcMutedStyle");
        card.Description.TextWrapping = TextWrapping.WrapWholeWords;
        card.Description.MaxLines = 3;
        card.Description.Margin = new Thickness(0, 4, 0, 0);
        card.State.Style = Resource<Style>("PdcCaptionStyle");
        card.State.Margin = new Thickness(0, 10, 0, 0);
        card.State.TextWrapping = TextWrapping.WrapWholeWords;
        card.Toggle.OnContent = string.Empty;
        card.Toggle.OffContent = string.Empty;
        card.Toggle.MinWidth = 0;
        card.Toggle.VerticalAlignment = VerticalAlignment.Center;
        card.Toggle.Toggled += (_, _) => _ = ToggleThemeAsync(card);
        card.Action.Style = Resource<Style>("PdcChipButtonStyle");
        card.Action.Padding = new Thickness(14, 9, 14, 9);
        card.Action.Margin = new Thickness(0, 12, 0, 0);
        card.Action.HorizontalAlignment = HorizontalAlignment.Left;
        card.Action.Click += (_, _) => _ = InstallAsync(card);
        card.OptionsButton.Style = Resource<Style>("PdcSoftButtonStyle");
        card.OptionsButton.Background = new SolidColorBrush(Windows.UI.Colors.Transparent);
        card.OptionsButton.Foreground = Resource<Brush>("PdcTextPrimaryBrush");
        card.OptionsButton.HorizontalAlignment = HorizontalAlignment.Stretch;
        card.OptionsButton.HorizontalContentAlignment = HorizontalAlignment.Left;
        card.OptionsButton.Padding = new Thickness(0, 10, 0, 4);
        card.OptionsButton.FontWeight = FontWeights.SemiBold;
        card.OptionsButton.Margin = new Thickness(0, 8, 0, 0);
        card.OptionsButton.Click += (_, _) =>
        {
            if (!expanded.Remove(card.Name))
            {
                expanded.Add(card.Name);
            }

            if (card.Entry is not null)
            {
                applying = true;
                try
                {
                    UpdateCard(card, card.Entry);
                }
                finally
                {
                    applying = false;
                }
            }
        };
        card.Options.Spacing = 14;
        card.Options.Margin = new Thickness(0, 8, 0, 4);

        var header = new Grid();
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.Children.Add(card.Title);
        Grid.SetColumn(card.Toggle, 1);
        header.Children.Add(card.Toggle);

        foreach (var option in theme.Options ?? new ThemeOption[0])
        {
            card.Options.Children.Add(BuildOption(card, option));
        }

        card.Root.Style = Resource<Style>("PdcCardStyle");
        card.Root.Child = new StackPanel
        {
            Children = { header, card.Description, card.State, card.Action, card.OptionsButton, card.Options },
        };
        return card;
    }

    private FrameworkElement BuildOption(ThemeCard card, ThemeOption option)
    {
        var label = LocalizedText.Pick(option.Label, language) ?? option.Name;
        string ValueLabel(ThemeOptionValue value) => LocalizedText.Pick(value.Label, language) ?? value.Value;
        switch (option.Type)
        {
            case "none":
                return new TextBlock
                {
                    Text = label.ToUpperInvariant(),
                    Style = Resource<Style>("PdcCaptionStyle"),
                    Margin = new Thickness(0, 6, 0, -6),
                    CharacterSpacing = 60,
                };
            case "checkbox":
                var toggle = new ToggleSwitch { Header = label, OnContent = string.Empty, OffContent = string.Empty, Tag = option.Name };
                toggle.Toggled += (_, _) =>
                {
                    var on = option.Values.FirstOrDefault(value => value.Value == "Yes")?.Value ?? option.Values.Last().Value;
                    var off = option.Values.FirstOrDefault(value => value.Value == "No")?.Value ?? option.Values.First().Value;
                    _ = SetOptionAsync(card, option.Name, toggle.IsOn ? on : off);
                };
                card.OptionControls[option.Name] = toggle;
                return toggle;
            case "slider" when option.Values.Length <= 4:
                var segments = new Grid { ColumnSpacing = 4, Tag = option.Name };
                foreach (var value in option.Values)
                {
                    segments.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    var chip = new Button { Content = ValueLabel(value), Tag = value.Value, Style = Resource<Style>("PdcSegmentButtonStyle") };
                    AutomationProperties.SetName(chip, $"{label}: {ValueLabel(value)}");
                    chip.Click += (_, _) => _ = SetOptionAsync(card, option.Name, value.Value);
                    Grid.SetColumn(chip, segments.ColumnDefinitions.Count - 1);
                    segments.Children.Add(chip);
                }

                card.OptionControls[option.Name] = segments;
                return new StackPanel
                {
                    Spacing = 6,
                    Children = { new TextBlock { Text = label, Style = Resource<Style>("PdcBodyStyle") }, new Border { Background = Resource<Brush>("PdcLayerBrush"), CornerRadius = new CornerRadius(12), Padding = new Thickness(3), Child = segments } },
                };
            default:
                var combo = new ComboBox { Header = label, HorizontalAlignment = HorizontalAlignment.Stretch, Tag = option.Name };
                foreach (var value in option.Values)
                {
                    combo.Items.Add(new ComboBoxItem { Content = ValueLabel(value), Tag = value.Value });
                }

                combo.SelectionChanged += (_, _) =>
                {
                    if (combo.SelectedItem is ComboBoxItem { Tag: string value })
                    {
                        _ = SetOptionAsync(card, option.Name, value);
                    }
                };
                card.OptionControls[option.Name] = combo;
                return combo;
        }
    }

    private void UpdateCard(ThemeCard card, ThemeEntry theme)
    {
        card.Entry = theme;
        card.Title.Text = LocalizedText.Pick(theme.DisplayName, language) ?? theme.Name;
        card.Description.Text = LocalizedText.Pick(theme.Description, language) ?? string.Empty;
        card.Description.Visibility = card.Description.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        card.Toggle.Visibility = theme.Installed && theme.Broken is null ? Visibility.Visible : Visibility.Collapsed;
        card.Toggle.IsOn = theme.Enabled;
        card.Toggle.IsEnabled = !operationPending;
        AutomationProperties.SetName(card.Toggle, card.Title.Text);

        var (state, brush) = StateText(theme);
        card.State.Text = state;
        card.State.Foreground = Resource<Brush>(brush);

        string? action = null;
        if (theme.Broken is not null || !theme.Installed)
        {
            action = theme.PublishedVersion is null ? null : string.Format(Localized("ThemesInstallAction"), theme.PublishedVersion);
        }
        else if (theme.UpdateAvailable)
        {
            action = string.Format(Localized("ThemesUpdateAction"), theme.PublishedVersion);
        }

        card.Action.Content = card.Installing ? Localized("ThemesInstalling") : action;
        card.Action.Visibility = action is null && !card.Installing ? Visibility.Collapsed : Visibility.Visible;
        card.Action.IsEnabled = !operationPending;

        var hasOptions = theme.Installed && theme.Broken is null && (theme.Options?.Any(option => option.Type != "none") ?? false);
        card.OptionsButton.Visibility = hasOptions ? Visibility.Visible : Visibility.Collapsed;
        card.OptionsButton.Content = (expanded.Contains(theme.Name) ? "▴  " : "▾  ") + Localized("ThemesOptions");
        card.Options.Visibility = hasOptions && expanded.Contains(theme.Name) ? Visibility.Visible : Visibility.Collapsed;

        foreach (var option in theme.Options ?? new ThemeOption[0])
        {
            if (!card.OptionControls.TryGetValue(option.Name, out var control))
            {
                continue;
            }

            control.IsHitTestVisible = !operationPending;
            switch (control)
            {
                case ToggleSwitch toggle:
                    toggle.IsOn = option.Value == "Yes";
                    break;
                case ComboBox combo:
                    combo.SelectedItem = combo.Items.OfType<ComboBoxItem>().FirstOrDefault(item => (string)item.Tag == option.Value);
                    break;
                case Grid segments:
                    foreach (var chip in segments.Children.OfType<Button>())
                    {
                        var active = (string)chip.Tag == option.Value;
                        chip.Background = active ? Resource<Brush>("PdcLayerStrongBrush") : new SolidColorBrush(Windows.UI.Colors.Transparent);
                        chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
                    }

                    break;
            }
        }
    }

    private (string Text, string Brush) StateText(ThemeEntry theme)
    {
        if (theme.Broken is not null)
        {
            return (Localized("ThemesStateBroken"), "PdcDangerBrush");
        }

        if (!theme.Installed)
        {
            return (Localized("ThemesStateNotInstalled"), "PdcTextMutedBrush");
        }

        var version = string.Format(Localized("ThemesVersion"), theme.InstalledVersion);
        if (!theme.Enabled)
        {
            return (version, "PdcTextMutedBrush");
        }

        if (theme.Applied)
        {
            return ($"{version} · {string.Format(Localized("ThemesStateApplied"), theme.PagesApplied)}", "PdcOkBrush");
        }

        if (theme.PagesExpected == 0)
        {
            return ($"{version} · {Localized("ThemesStatePending")}", "PdcTextMutedBrush");
        }

        if (theme.PagesApplied < theme.PagesExpected)
        {
            return ($"{version} · {string.Format(Localized("ThemesStatePartial"), theme.PagesApplied, theme.PagesExpected)}", "PdcWarnBrush");
        }

        return ($"{version} · {Localized("ThemesStateRuntimeMissing")}", "PdcWarnBrush");
    }

    private async void ConnectionAction_Click(object sender, RoutedEventArgs args)
    {
        await RunAsync(() => client.RestartSteamAsync());
    }

    private async Task ToggleThemeAsync(ThemeCard card)
    {
        if (applying || card.Entry is null || card.Toggle.IsOn == card.Entry.Enabled)
        {
            return;
        }

        var enabled = card.Toggle.IsOn;
        await RunAsync(() => client.SetEnabledAsync(card.Name, enabled));
    }

    private async Task InstallAsync(ThemeCard card)
    {
        if (applying || card.Entry?.CatalogId is not { } catalogId || card.Entry.PublishedVersion is not { } version)
        {
            return;
        }

        card.Installing = true;
        try
        {
            await RunAsync(async () =>
            {
                var response = await client.InstallAsync(catalogId, version);
                var installed = response.Themes.FirstOrDefault(theme => theme.Name == card.Name);
                return response.Status == ThemesResponseStatus.Ok && installed is { Installed: true, Enabled: false } && card.Entry.InstalledVersion is null
                    ? await client.SetEnabledAsync(card.Name, true)
                    : response;
            });
        }
        finally
        {
            card.Installing = false;
            if (last is not null)
            {
                Apply(last, null);
            }
        }
    }

    private async Task SetOptionAsync(ThemeCard card, string option, string value)
    {
        if (applying)
        {
            return;
        }

        var current = card.Entry?.Options?.FirstOrDefault(candidate => candidate.Name == option);
        if (current?.Value == value)
        {
            return;
        }

        await RunAsync(() => client.SetOptionAsync(card.Name, option, value));
    }

    private async Task RunAsync(Func<Task<ThemesResponse>> operation)
    {
        if (operationPending)
        {
            return;
        }

        operationPending = true;
        if (last is not null)
        {
            Apply(last, null);
        }

        ThemesResponse response;
        try
        {
            response = await operation();
        }
        finally
        {
            operationPending = false;
        }

        Apply(response, response.Status == ThemesResponseStatus.Ok ? null : ErrorText(response.ErrorCode));
    }

    private static string ErrorText(string? code) => code switch
    {
        "artifact_hash_mismatch" or "artifact_size_mismatch" or "invalid_archive" or "unsafe_archive" or "invalid_package" or "identity_mismatch" =>
            Localized("ThemesErrorPackage"),
        "catalog_unavailable" or "publication_changed" => Localized("ThemesErrorCatalog"),
        "themes_timeout" or "themes_response_unavailable" => Localized("ThemesErrorTimeout"),
        _ => Localized("ThemesErrorGeneric"),
    };

    private static string UiLanguage()
    {
        try
        {
            return ResourceContext.GetForViewIndependentUse().QualifierValues["Language"].Split(';')[0];
        }
        catch
        {
            return "en";
        }
    }

    private static T Resource<T>(string key) => (T)Application.Current.Resources[key];

    private static string Localized(string key) => Strings.GetString(key);

    private sealed class ThemeCard
    {
        public ThemeCard(string name)
        {
            Name = name;
        }

        public string Name { get; }

        public ThemeEntry? Entry { get; set; }

        public bool Installing { get; set; }

        public Border Root { get; } = new();

        public TextBlock Title { get; } = new();

        public TextBlock Description { get; } = new();

        public TextBlock State { get; } = new();

        public ToggleSwitch Toggle { get; } = new();

        public Button Action { get; } = new();

        public Button OptionsButton { get; } = new();

        public StackPanel Options { get; } = new();

        public Dictionary<string, FrameworkElement> OptionControls { get; } = new(StringComparer.Ordinal);
    }
}
