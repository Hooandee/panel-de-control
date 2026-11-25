using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Threading;
using System.Threading.Tasks;
using PanelDeControl.Core.Upscalers;
using Windows.ApplicationModel.Resources;
using Windows.Storage.Streams;
using Windows.UI;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Automation.Peers;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Media.Imaging;

namespace PanelDeControl.GameBar;

/// <summary>
/// Escaladores on Windows, experimental: installed Steam games, one view per game with the build and quality to
/// install, and the real outcome of the companion's install or removal job.
/// </summary>
public sealed partial class UpscalersView : UserControl
{
    private static readonly ResourceLoader Strings = ResourceLoader.GetForViewIndependentUse();
    private static readonly string[] Qualities = { "native", "quality", "balanced", "performance" };
    private static readonly string[] OwnInputs = { "dlss", "fsr31", "fsr2", "xess" };
    private const string DefaultQuality = "quality";
    private const int MaximumPollFailures = 12;
    private const int MaximumCoverRequests = 2;
    private const int EagerRows = 6;
    private const double PrefetchDistance = 240;

    private readonly UpscalersClient client = new();
    private readonly DispatcherTimer pollTimer = new() { Interval = TimeSpan.FromMilliseconds(500) };
    private readonly ToggleSwitch experimentalToggle = new();
    private readonly StackPanel content = new() { Spacing = 10, Visibility = Visibility.Collapsed };
    private readonly StackPanel listPanel = new() { Spacing = 10 };
    private readonly TextBlock gpuText = new();
    private readonly TextBlock statusText = new();
    private readonly StackPanel gameList = new() { Spacing = 4 };
    private readonly StackPanel gamePanel = new() { Spacing = 10, Visibility = Visibility.Collapsed };
    private readonly Button backButton = new();
    private readonly Border headerCover = new();
    private readonly Image headerImage = new();
    private readonly TextBlock detailTitle = new();
    private readonly TextBlock detailSubtitle = new();
    private readonly TextBlock statusTitle = new();
    private readonly TextBlock statusSub = new();
    private readonly StackPanel pickerPanel = new() { Spacing = 6 };
    private readonly TextBlock buildLabel = new();
    private readonly StackPanel buildList = new() { Spacing = 4 };
    private readonly StackPanel qualityPanel = new() { Spacing = 6 };
    private readonly TextBlock qualityLabel = new();
    private readonly Grid qualityRow = new() { ColumnSpacing = 4 };
    private readonly Border qualityHost;
    private readonly TextBlock hintText = new();
    private readonly Button actionButton = new();
    private readonly StackPanel progressPanel = new() { Spacing = 6, Visibility = Visibility.Collapsed };
    private readonly ProgressBar progressBar = new() { Minimum = 0, Maximum = 1 };
    private readonly TextBlock progressText = new();
    private readonly TextBlock resultText = new();
    private readonly Button advancedButton = new();
    private readonly StackPanel advancedPanel = new() { Spacing = 4, Visibility = Visibility.Collapsed };
    private readonly TextBlock advancedExe = new();
    private readonly TextBlock advancedApis = new();
    private readonly Dictionary<string, Task<BitmapImage?>> covers = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim coverGate = new(MaximumCoverRequests);

    private UpscalerGameSummary[] games = Array.Empty<UpscalerGameSummary>();
    private UpscalerGameDetail? detail;
    private string gpuFamily = "unknown";
    private string? selectedAppId;
    private string? selectedBuild;
    private string? selectedModel;
    private string selectedQuality = DefaultQuality;
    private bool advancedOpen;
    private bool refreshing;
    private bool loadingGame;
    private bool jobRunning;
    private bool polling;
    private bool progressShown;
    private int pollFailures;
    private string jobKind = "";
    private string jobAppId = "";
    private long selectionGeneration;

    public UpscalersView()
    {
        var experimentalLabel = new TextBlock
        {
            Style = Resource<Style>("PdcBodyStyle"),
            VerticalAlignment = VerticalAlignment.Center,
            Text = Localized("UpscalersExperimentalLabel"),
        };
        experimentalToggle.OnContent = string.Empty;
        experimentalToggle.OffContent = string.Empty;
        experimentalToggle.MinWidth = 0;
        experimentalToggle.Width = 44;
        experimentalToggle.HorizontalAlignment = HorizontalAlignment.Right;
        AutomationProperties.SetName(experimentalToggle, Localized("UpscalersExperimentalName"));
        AutomationProperties.SetHelpText(experimentalToggle, Localized("UpscalersExperimentalHelp"));
        experimentalToggle.Toggled += ExperimentalToggle_Toggled;

        var header = new Grid { ColumnSpacing = 12 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.Children.Add(experimentalLabel);
        Grid.SetColumn(experimentalToggle, 1);
        header.Children.Add(experimentalToggle);

        var intro = Muted(Localized("UpscalersIntro"));
        intro.Margin = new Thickness(0, 4, 0, 0);

        gpuText.Style = Resource<Style>("PdcCaptionStyle");
        gpuText.TextWrapping = TextWrapping.WrapWholeWords;
        statusText.Style = Resource<Style>("PdcMutedStyle");
        statusText.TextWrapping = TextWrapping.WrapWholeWords;

        backButton.Style = Resource<Style>("PdcChipButtonStyle");
        backButton.Content = "‹  " + Localized("UpscalersBack");
        backButton.HorizontalAlignment = HorizontalAlignment.Left;
        backButton.Padding = new Thickness(12, 8, 12, 8);
        AutomationProperties.SetName(backButton, Localized("UpscalersBack"));
        backButton.Click += BackButton_Click;

        BuildCover(headerCover, headerImage, 48, 72);
        detailTitle.Style = Resource<Style>("PdcTitleStyle");
        detailTitle.TextWrapping = TextWrapping.WrapWholeWords;
        detailSubtitle.Style = Resource<Style>("PdcMutedStyle");
        detailSubtitle.TextWrapping = TextWrapping.WrapWholeWords;
        var titles = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center, Children = { detailTitle, detailSubtitle } };
        var identity = new Grid { ColumnSpacing = 12 };
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        identity.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        identity.Children.Add(headerCover);
        Grid.SetColumn(titles, 1);
        identity.Children.Add(titles);

        statusTitle.Style = Resource<Style>("PdcBodyStyle");
        statusTitle.FontWeight = FontWeights.SemiBold;
        statusTitle.TextWrapping = TextWrapping.WrapWholeWords;
        statusSub.Style = Resource<Style>("PdcCaptionStyle");
        statusSub.TextWrapping = TextWrapping.WrapWholeWords;
        var statusCard = Card(new StackPanel { Spacing = 4, Children = { statusTitle, statusSub } });

        buildLabel.Style = Resource<Style>("PdcBodyStyle");
        buildLabel.Text = Localized("UpscalersBuildLabel");
        pickerPanel.Children.Add(buildLabel);
        pickerPanel.Children.Add(buildList);
        qualityLabel.Style = Resource<Style>("PdcBodyStyle");
        qualityLabel.Text = Localized("UpscalersQualityLabel");
        for (var index = 0; index < Qualities.Length; index++)
        {
            qualityRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var chip = new Button
            {
                Tag = Qualities[index],
                Content = Localized("UpscalersQuality_" + Qualities[index]),
                Style = Resource<Style>("PdcSegmentButtonStyle"),
            };
            chip.Click += QualityChip_Click;
            Grid.SetColumn(chip, index);
            qualityRow.Children.Add(chip);
        }

        qualityHost = new Border
        {
            Padding = new Thickness(4),
            CornerRadius = Resource<CornerRadius>("PdcRadiusInset"),
            Background = Resource<Brush>("PdcLayerBrush"),
            Child = qualityRow,
        };
        qualityPanel.Children.Add(qualityLabel);
        qualityPanel.Children.Add(qualityHost);

        hintText.Style = Resource<Style>("PdcCaptionStyle");
        hintText.TextWrapping = TextWrapping.WrapWholeWords;
        hintText.Foreground = Resource<Brush>("PdcWarnBrush");
        actionButton.Style = Resource<Style>("PdcChipButtonStyle");
        actionButton.Padding = new Thickness(14, 10, 14, 10);
        actionButton.HorizontalAlignment = HorizontalAlignment.Stretch;
        actionButton.HorizontalContentAlignment = HorizontalAlignment.Center;
        actionButton.FontWeight = FontWeights.SemiBold;
        actionButton.Click += ActionButton_Click;

        progressText.Style = Resource<Style>("PdcCaptionStyle");
        progressText.TextWrapping = TextWrapping.WrapWholeWords;
        progressBar.Foreground = Resource<Brush>("PdcAccentBrush");
        AutomationProperties.SetLiveSetting(progressText, AutomationLiveSetting.Polite);
        progressPanel.Children.Add(progressText);
        progressPanel.Children.Add(progressBar);
        progressPanel.Children.Add(BuildCancelButton());
        resultText.Style = Resource<Style>("PdcCaptionStyle");
        resultText.TextWrapping = TextWrapping.WrapWholeWords;
        AutomationProperties.SetLiveSetting(resultText, AutomationLiveSetting.Polite);

        advancedButton.Style = Resource<Style>("PdcSoftButtonStyle");
        advancedButton.Background = new SolidColorBrush(Colors.Transparent);
        advancedButton.Foreground = Resource<Brush>("PdcTextMutedBrush");
        advancedButton.HorizontalAlignment = HorizontalAlignment.Left;
        advancedButton.Padding = new Thickness(0, 8, 8, 8);
        advancedButton.Click += AdvancedButton_Click;
        foreach (var line in new[] { advancedExe, advancedApis })
        {
            line.Style = Resource<Style>("PdcCaptionStyle");
            line.TextWrapping = TextWrapping.WrapWholeWords;
            advancedPanel.Children.Add(line);
        }

        advancedPanel.Children.Add(BuildExeEditor());
        advancedPanel.Children.Add(BuildIniEditor());

        gamePanel.Children.Add(backButton);
        gamePanel.Children.Add(identity);
        gamePanel.Children.Add(statusCard);
        gamePanel.Children.Add(BuildVerifyButton());
        gamePanel.Children.Add(BuildForeignButtons());
        gamePanel.Children.Add(pickerPanel);
        gamePanel.Children.Add(qualityPanel);
        gamePanel.Children.Add(hintText);
        gamePanel.Children.Add(actionButton);
        gamePanel.Children.Add(progressPanel);
        gamePanel.Children.Add(resultText);
        gamePanel.Children.Add(BuildSettingsPanel());
        gamePanel.Children.Add(advancedButton);
        gamePanel.Children.Add(advancedPanel);

        listPanel.Children.Add(gpuText);
        listPanel.Children.Add(statusText);
        listPanel.Children.Add(gameList);
        content.Children.Add(listPanel);
        content.Children.Add(gamePanel);
        foreach (var line in new[] { gpuText, statusText, hintText, resultText, statusSub, detailSubtitle, advancedExe, advancedApis })
        {
            CollapseWhenEmpty(line);
        }

        var stack = new StackPanel { Children = { header, intro, new Border { Margin = new Thickness(0, 12, 0, 0), Child = content } } };
        Content = new Border { Style = Resource<Style>("PdcCardStyle"), Child = stack };

        pollTimer.Tick += PollTimer_Tick;
        Unloaded += (_, _) => pollTimer.Stop();
    }

    private bool Experimental => experimentalToggle.IsOn;

    public Task RefreshAsync() => RefreshAsync(reloadGame: true);

    /// <summary>
    /// The widget's periodic refresh: keeps the list and a running job current without reloading the open game, which
    /// would disable its buttons every two seconds.
    /// </summary>
    public Task RefreshListAsync() => RefreshAsync(reloadGame: false);

    private async Task RefreshAsync(bool reloadGame)
    {
        if (!Experimental || refreshing || jobRunning)
        {
            return;
        }

        refreshing = true;
        try
        {
            var job = await client.JobAsync();
            if (job.Status == UpscalersResponseStatus.Ok && job.Job is { State: UpscalerJobStates.Running } running)
            {
                await ResumeJobAsync(running);
                return;
            }

            // An open game page is not redrawn by the periodic refresh: it would lose the scroll and the focus.
            if (reloadGame || selectedAppId is null)
            {
                await LoadOverviewAsync(reloadGame);
            }
        }
        finally
        {
            refreshing = false;
        }
    }

    private async void ExperimentalToggle_Toggled(object sender, RoutedEventArgs args)
    {
        content.Visibility = Experimental ? Visibility.Visible : Visibility.Collapsed;
        if (Experimental)
        {
            statusText.Text = Localized("UpscalersLoading");
            await RefreshAsync();
        }
        else
        {
            ShowResult(string.Empty, true);
            CloseGame();
        }
    }

    private async Task LoadOverviewAsync(bool reloadGame = true)
    {
        var response = await client.OverviewAsync();
        if (!Experimental)
        {
            return;
        }

        foreach (var failed in covers.Where(entry => entry.Value.IsCompleted && entry.Value.Result is null).Select(entry => entry.Key).ToList())
        {
            covers.Remove(failed);
        }

        if (response.Status != UpscalersResponseStatus.Ok || response.Overview is null)
        {
            games = Array.Empty<UpscalerGameSummary>();
            gpuText.Text = string.Empty;
            statusText.Text = ErrorMessage(response.ErrorCode);
            RenderGames();
            RenderView();
            return;
        }

        var overview = response.Overview;
        games = overview.Games.OrderBy(game => game.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();
        gpuFamily = overview.Gpu;
        var gpu = !string.IsNullOrWhiteSpace(overview.GpuName)
            ? overview.GpuName!
            : overview.Gpu == "unknown" ? Localized("UpscalersGpuUnknown") : overview.Gpu;
        gpuText.Text = string.Format(Localized("UpscalersGpu"), gpu);
        statusText.Text = !overview.SteamFound
            ? Localized("UpscalersNoSteam")
            : games.Length == 0 ? Localized("UpscalersNoGames") : string.Empty;
        if (selectedAppId is not null && games.All(game => game.AppId != selectedAppId))
        {
            selectedAppId = null;
            detail = null;
        }

        RenderGames();
        if (selectedAppId is not null && reloadGame)
        {
            await LoadGameAsync();
        }
        else
        {
            RenderView();
        }
    }

    private void RenderGames()
    {
        gameList.Children.Clear();
        var position = 0;
        foreach (var game in games)
        {
            var image = new Image { Stretch = Stretch.UniformToFill };
            var cover = new Border();
            BuildCover(cover, image, 32, 48);
            var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            text.Children.Add(new TextBlock { Text = game.Name, Style = Resource<Style>("PdcBodyStyle"), TextTrimming = TextTrimming.CharacterEllipsis });
            var state = GameState(game);
            if (state.Length > 0)
            {
                text.Children.Add(new TextBlock { Text = state, Style = Resource<Style>("PdcCaptionStyle"), TextWrapping = TextWrapping.WrapWholeWords });
            }

            var row = new Grid { ColumnSpacing = 12 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.Children.Add(cover);
            Grid.SetColumn(text, 1);
            row.Children.Add(text);
            var button = new Button
            {
                Tag = game.AppId,
                Content = row,
                Style = Resource<Style>("PdcChipButtonStyle"),
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Padding = new Thickness(10, 8, 12, 8),
                IsEnabled = !jobRunning,
                Background = Resource<Brush>("PdcLayerBrush"),
            };
            AutomationProperties.SetName(button, game.Name + (state.Length > 0 ? ". " + state : string.Empty));
            button.Click += GameButton_Click;
            LoadCoverWhenVisible(button, image, game.AppId, position++ < EagerRows);
            gameList.Children.Add(button);
        }
    }

    private static string GameState(UpscalerGameSummary game)
    {
        var parts = new List<string>();
        switch (game.State)
        {
            case UpscalerGameStates.Installed:
                parts.Add(!string.IsNullOrEmpty(game.Label) ? game.Label! : Localized("UpscalersStateInstalled"));
                break;
            case UpscalerGameStates.Missing:
                parts.Add(Localized("UpscalersStateMissing"));
                break;
            case UpscalerGameStates.Foreign:
                parts.Add(Localized("UpscalersStateForeign"));
                break;
            case UpscalerGameStates.PanelUnknown:
                parts.Add(Localized("UpscalersStateInstalledUnknown"));
                break;
        }

        if (game.Running == true)
        {
            parts.Add(Localized("UpscalersStateRunning"));
        }

        if (game.Updating)
        {
            parts.Add(Localized("UpscalersStateUpdating"));
        }

        return string.Join(" · ", parts);
    }

    private void BuildCover(Border host, Image image, double width, double height)
    {
        host.Width = width;
        host.Height = height;
        host.CornerRadius = new CornerRadius(4);
        host.Background = Resource<Brush>("PdcLayerStrongBrush");
        host.VerticalAlignment = VerticalAlignment.Center;
        host.Child = image;
        image.Stretch = Stretch.UniformToFill;
        AutomationProperties.SetAccessibilityView(host, AccessibilityView.Raw);
    }

    private void LoadCoverWhenVisible(FrameworkElement trigger, Image image, string appId, bool immediately)
    {
        var requested = false;
        async void Request()
        {
            if (requested)
            {
                return;
            }

            requested = true;
            if (await CoverAsync(appId) is { } bitmap)
            {
                image.Source = bitmap;
            }
        }

        if (immediately)
        {
            trigger.Loaded += (_, _) => Request();
        }

        trigger.EffectiveViewportChanged += (_, args) =>
        {
            if (args.BringIntoViewDistanceY <= PrefetchDistance)
            {
                Request();
            }
        };
    }

    private Task<BitmapImage?> CoverAsync(string appId)
    {
        if (!covers.TryGetValue(appId, out var task))
        {
            task = FetchCoverAsync(appId);
            covers[appId] = task;
        }

        return task;
    }

    private async Task<BitmapImage?> FetchCoverAsync(string appId)
    {
        await coverGate.WaitAsync();
        try
        {
            var response = await client.CoverAsync(appId);
            if (response.Status != UpscalersResponseStatus.Ok || response.Cover is not { } cover)
            {
                return null;
            }

            var bitmap = new BitmapImage();
            using var stream = new InMemoryRandomAccessStream();
            await stream.WriteAsync(Convert.FromBase64String(cover.Data).AsBuffer());
            stream.Seek(0);
            await bitmap.SetSourceAsync(stream);
            return bitmap;
        }
        catch
        {
            return null;
        }
        finally
        {
            coverGate.Release();
        }
    }

    private async void GameButton_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: string appId })
        {
            return;
        }

        selectedAppId = appId;
        selectionGeneration++;
        detail = null;
        ShowResult(string.Empty, true);
        RenderView();
        backButton.Focus(FocusState.Programmatic);
        await LoadGameAsync();
    }

    private void BackButton_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning)
        {
            return;
        }

        var appId = selectedAppId;
        CloseGame();
        if (appId is not null)
        {
            gameList.Children.OfType<Button>().FirstOrDefault(button => Equals(button.Tag, appId))?.Focus(FocusState.Programmatic);
        }
    }

    private void CloseGame()
    {
        selectedAppId = null;
        selectionGeneration++;
        detail = null;
        loadingGame = false;
        ShowResult(string.Empty, true);
        ResetSettings();
        RenderView();
    }

    private void AdvancedButton_Click(object sender, RoutedEventArgs args)
    {
        advancedOpen = !advancedOpen;
        RenderAdvanced();
        if (advancedOpen)
        {
            _ = LoadIniAsync();
        }
    }

    private async Task LoadGameAsync()
    {
        var appId = selectedAppId;
        if (appId is null)
        {
            return;
        }

        var generation = selectionGeneration;
        loadingGame = true;
        RenderView();
        var response = await client.GameAsync(appId);
        loadingGame = false;
        if (generation != selectionGeneration || appId != selectedAppId || !Experimental)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Game is not null)
        {
            detail = response.Game;
            var installed = detail.Install;
            selectedBuild = installed?.Build is { } build && detail.Builds.Any(entry => entry.Id == build)
                ? build
                : detail.Builds.Any(entry => entry.Id == selectedBuild)
                    ? selectedBuild
                    : detail.Preferred is { } preferred && detail.Builds.Any(entry => entry.Id == preferred)
                        ? preferred
                        : detail.Builds.FirstOrDefault()?.Id;
            var models = detail.Builds.FirstOrDefault(entry => entry.Id == selectedBuild)?.Models ?? Array.Empty<string>();
            selectedModel = installed?.Build == selectedBuild && installed?.Model is { } model && models.Contains(model)
                ? model
                : selectedModel is not null && models.Contains(selectedModel) ? selectedModel : models.FirstOrDefault();
            if (installed is not null)
            {
                // A quality outside the chips (or none) stays as installed: no chip is lit and none is sent.
                selectedQuality = installed.Quality is { } quality && Qualities.Contains(quality) ? quality : string.Empty;
            }
            else if (selectedQuality.Length == 0)
            {
                selectedQuality = DefaultQuality;
            }
        }
        else
        {
            detail = null;
            ShowResult(ErrorMessage(response.ErrorCode), false);
        }

        RenderView();
        if (detail is not null)
        {
            await LoadSettingsAsync(appId, generation);
        }
    }

    private void RenderView()
    {
        var inGame = selectedAppId is not null;
        listPanel.Visibility = inGame ? Visibility.Collapsed : Visibility.Visible;
        gamePanel.Visibility = inGame ? Visibility.Visible : Visibility.Collapsed;
        if (!inGame)
        {
            UpdateActionState();
            return;
        }

        var summary = games.FirstOrDefault(game => game.AppId == selectedAppId);
        detailTitle.Text = summary?.Name ?? string.Empty;
        detailSubtitle.Text = Subtitle(summary);
        if (!headerCoverLoaded.Equals(selectedAppId))
        {
            headerCoverLoaded = selectedAppId!;
            headerImage.Source = null;
            _ = ShowHeaderCoverAsync(selectedAppId!);
        }

        RenderStatus();
        var choosing = detail is not null && detail.Install is null;
        var choice = choosing ? Visibility.Visible : Visibility.Collapsed;
        pickerPanel.Visibility = choice;
        qualityPanel.Visibility = choosing || OptiScalerInstalled ? Visibility.Visible : Visibility.Collapsed;
        RenderBuilds();
        RenderAdvanced();
        UpdateActionState();
    }

    private string headerCoverLoaded = string.Empty;

    private async Task ShowHeaderCoverAsync(string appId)
    {
        if (await CoverAsync(appId) is { } bitmap && appId == selectedAppId)
        {
            headerImage.Source = bitmap;
        }
    }

    private string Subtitle(UpscalerGameSummary? summary)
    {
        if (detail is null)
        {
            return string.Empty;
        }

        if (detail.Install is { Status: UpscalerGameStates.Installed } installed && !string.IsNullOrEmpty(installed.Label))
        {
            return installed.Label!;
        }

        if (detail.Install is { Status: UpscalerGameStates.Installed, Build.Length: 0 })
        {
            return string.Empty;
        }

        if (detail.Foreign is not null || summary?.State == UpscalerGameStates.Foreign)
        {
            return Localized("UpscalersStateForeign");
        }

        var uses = detail.Inputs.Select(input => input.Kind).Where(OwnInputs.Contains).Select(InputName).Distinct().ToArray();
        return uses.Length > 0 ? string.Format(Localized("UpscalersSubUses"), string.Join(", ", uses)) : string.Empty;
    }

    private static string InputName(string kind) => kind switch
    {
        "dlss" => "DLSS",
        "helixsr" => "HLX",
        "fsr31" => "FSR 3.1",
        "fsr2" => "FSR 2",
        _ => "XeSS",
    };

    private void RenderStatus()
    {
        var title = string.Empty;
        var sub = string.Empty;
        if (detail is null)
        {
            title = loadingGame ? Localized("UpscalersLoading") : string.Empty;
        }
        else if (detail.Install is { } installed)
        {
            if (installed.Status == UpscalerGameStates.Missing)
            {
                title = Localized("UpscalersStateMissing");
            }
            else
            {
                title = !string.IsNullOrEmpty(installed.Label)
                    ? string.Format(Localized("UpscalersStatusInstalled"), DllLabel(installed.Build, installed.Label!))
                    : Localized(installed.Build.Length == 0 ? "UpscalersStateInstalledUnknown" : "UpscalersStateInstalled");
                sub = installed.Verdict is "active" or "loaded"
                    ? string.Join(" · ", new[] { Localized("UpscalersVerdict_" + installed.Verdict), installed.Provider }.Where(part => !string.IsNullOrEmpty(part)))
                    : resultText.Text.Length == 0 && installed.Build.Length != 0
                        ? Localized(IsDll(installed.Build) ? "UpscalersDllCheck" : "UpscalersStatusPending")
                        : string.Empty;
            }
        }
        else if (detail.Foreign is not null || detail.Game.State == UpscalerGameStates.Foreign)
        {
            title = Localized("UpscalersForeignTitle");
            sub = Localized("UpscalersErrForeign");
        }
        else
        {
            title = Localized("UpscalersStatusNone");
        }

        statusTitle.Text = title;
        statusSub.Text = sub;
    }

    private void RenderAdvanced()
    {
        var exe = detail?.Exe;
        var apis = detail is null ? Array.Empty<string>() : detail.Apis.Where(api => !string.Equals(api, "dxgi", StringComparison.OrdinalIgnoreCase)).ToArray();
        var any = !string.IsNullOrEmpty(exe) || apis.Length > 0;
        advancedButton.Visibility = any ? Visibility.Visible : Visibility.Collapsed;
        advancedButton.Content = (advancedOpen ? "▾  " : "▸  ") + Localized("UpscalersAdvanced");
        AutomationProperties.SetName(advancedButton, Localized("UpscalersAdvanced"));
        advancedPanel.Visibility = any && advancedOpen ? Visibility.Visible : Visibility.Collapsed;
        advancedExe.Text = string.IsNullOrEmpty(exe) ? string.Empty : Localized("UpscalersExe") + ": " + exe;
        advancedApis.Text = apis.Length == 0 ? string.Empty : Localized("UpscalersApis") + ": " + string.Join(", ", apis);
    }

    private sealed class BuildOption
    {
        public BuildOption(UpscalerBuildEntry build, string? model, string label, string? note)
        {
            Build = build;
            Model = model;
            Label = label;
            Note = note;
        }

        public UpscalerBuildEntry Build { get; }

        public string? Model { get; }

        public string Label { get; }

        public string? Note { get; }
    }

    private List<BuildOption> Options()
    {
        var options = new List<BuildOption>();
        if (detail is null)
        {
            return options;
        }

        var shown = new List<UpscalerBuildEntry>();
        foreach (var build in detail.Builds.OrderByDescending(entry => entry.Supported))
        {
            if (!build.Supported)
            {
                if (gpuFamily.StartsWith("rdna", StringComparison.Ordinal))
                {
                    if (detail.Builds.Any(other => other.Supported && other.Family == build.Family && other.Version == build.Version))
                    {
                        continue;
                    }
                }
                else if (shown.Any(other => !other.Supported && other.Family == build.Family && other.Version == build.Version && other.Channel == build.Channel))
                {
                    continue;
                }
            }

            shown.Add(build);
        }

        foreach (var build in shown)
        {
            var name = FamilyName(build.Family) + " " + build.Version + (build.Channel == "beta" ? " " + Localized("UpscalersBeta") : string.Empty)
                + (build.Engine == "dll" ? " · " + Localized("UpscalersDllMode") : string.Empty);
            var note = new List<string>();
            if (build.Id == detail.Preferred)
            {
                note.Add(Localized("UpscalersRecommended"));
            }

            if (!build.Supported)
            {
                note.Add(Localized("UpscalersUntested"));
            }

            if (build.DownloadBytes > 0)
            {
                note.Add(string.Format(Localized("UpscalersMegabytes"), Megabytes(build.DownloadBytes)));
            }

            var joined = note.Count > 0 ? string.Join(" · ", note) : null;
            if (build.Models.Length == 0)
            {
                options.Add(new BuildOption(build, null, name, joined));
                continue;
            }

            foreach (var model in build.Models)
            {
                options.Add(new BuildOption(build, model, name + " " + (model == "full" ? Localized("UpscalersModel_full") : model == "lite" ? "Lite" : model), joined));
            }
        }

        var repeated = options.GroupBy(option => option.Label).Where(group => group.Count() > 1).Select(group => group.Key).ToHashSet();
        return options
            .Select(option => repeated.Contains(option.Label) && option.Build.Id.Contains("rdna2", StringComparison.Ordinal)
                ? new BuildOption(option.Build, option.Model, option.Label + " · RDNA 2", option.Note)
                : option)
            .ToList();
    }

    private void RenderBuilds()
    {
        buildList.Children.Clear();
        if (detail is null || detail.Install is not null)
        {
            return;
        }

        foreach (var option in Options())
        {
            var text = new StackPanel();
            text.Children.Add(new TextBlock { Text = option.Label, Style = Resource<Style>("PdcBodyStyle"), TextWrapping = TextWrapping.WrapWholeWords });
            if (option.Note is not null)
            {
                text.Children.Add(new TextBlock { Text = option.Note, Style = Resource<Style>("PdcCaptionStyle"), TextWrapping = TextWrapping.WrapWholeWords });
            }

            var chip = new Button
            {
                Tag = option,
                Content = text,
                Style = Resource<Style>("PdcChipButtonStyle"),
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Padding = new Thickness(12, 8, 12, 8),
            };
            AutomationProperties.SetName(chip, option.Label + (option.Note is not null ? ". " + option.Note : string.Empty));
            chip.Click += BuildChip_Click;
            buildList.Children.Add(chip);
        }
    }

    private static string FamilyName(string family) => family switch
    {
        "fsr" => "FSR",
        "xess" => "XeSS",
        "dlss" => "DLSS",
        "helixsr" => "HLX",
        _ => family,
    };

    private void BuildChip_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: BuildOption option })
        {
            return;
        }

        selectedBuild = option.Build.Id;
        selectedModel = option.Model;
        ClearResult();
        UpdateActionState();
    }

    private void QualityChip_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: string quality })
        {
            return;
        }

        selectedQuality = quality;
        ClearResult();
        UpdateActionState();
    }

    private bool IsHelix(string build) => detail?.Builds.FirstOrDefault(entry => entry.Id == build)?.Engine == "helixsr";

    private bool IsDll(string build) => detail?.Builds.FirstOrDefault(entry => entry.Id == build)?.Engine == "dll";

    private string DllLabel(string build, string label) => IsDll(build) ? label + " · " + Localized("UpscalersDllMode") : label;

    private string SelectedBadge()
    {
        var build = detail?.Builds.FirstOrDefault(entry => entry.Id == selectedBuild);
        return build is null
            ? string.Empty
            : UpscalerLabel.Badge(build.Family, build.Version, build.Models, selectedModel);
    }

    private void UpdateActionState()
    {
        foreach (var chip in buildList.Children.OfType<Button>())
        {
            var active = chip.Tag is BuildOption option && option.Build.Id == selectedBuild && option.Model == selectedModel;
            chip.Background = active ? AccentFill() : Resource<Brush>("PdcLayerBrush");
            chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
            chip.IsEnabled = !jobRunning;
        }

        // In the DLL mode the game's own menu sets the quality, as on Linux.
        var dllChosen = selectedBuild is not null && IsDll(selectedBuild);
        var helixChosen = selectedBuild is not null && IsHelix(selectedBuild);
        qualityHost.Visibility = dllChosen || helixChosen ? Visibility.Collapsed : Visibility.Visible;
        qualityLabel.Text = Localized(helixChosen ? "UpscalersHelixPick" : dllChosen ? "UpscalersDllNoOptions" : "UpscalersQualityLabel");
        foreach (var chip in qualityRow.Children.OfType<Button>())
        {
            var active = Equals(chip.Tag, selectedQuality);
            chip.Background = active ? AccentFill() : new SolidColorBrush(Colors.Transparent);
            chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
            chip.IsEnabled = !jobRunning;
        }

        foreach (var chip in gameList.Children.OfType<Button>())
        {
            chip.IsEnabled = !jobRunning;
        }

        experimentalToggle.IsEnabled = !jobRunning;
        backButton.IsEnabled = !jobRunning;
        string? reason = null;
        if (detail is not null)
        {
            var summary = detail.Game;
            var installed = detail.Install is not null;
            actionButton.Content = loadingGame
                ? Localized("UpscalersLoading")
                : installed
                    ? detail.Install!.Build.Length == 0
                        ? Localized("UpscalersDeactivatePlain")
                        : string.Format(Localized("UpscalersDeactivate"), !string.IsNullOrEmpty(detail.Install.Label) ? detail.Install.Label : Localized("UpscalersStateInstalled"))
                    : string.Format(Localized("UpscalersActivate"), SelectedBadge());
            actionButton.Background = installed ? Resource<Brush>("PdcLayerBrush") : AccentFill();
            if (summary.Running == true)
            {
                reason = "running";
            }
            else if (summary.Updating)
            {
                reason = "updating";
            }
            else if (!installed)
            {
                if (summary.State == UpscalerGameStates.Foreign || detail.Foreign is not null)
                {
                    reason = "foreign";
                }
                else if (detail.AntiCheat)
                {
                    reason = "anti_cheat";
                }
                else if (detail.Recipe is { Installable: false })
                {
                    reason = "recipe_unsupported";
                }
                else if (selectedBuild is null)
                {
                    reason = "no_builds";
                }
            }
        }

        actionButton.Visibility = detail is not null ? Visibility.Visible : Visibility.Collapsed;
        hintText.Text = !jobRunning && reason is not null ? ErrorMessage(reason) : string.Empty;
        actionButton.IsEnabled = detail is not null && !jobRunning && !loadingGame && !settingsBusy && reason is null;
        RenderSettings();
        RenderGameExtras();
    }

    private async void ActionButton_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || detail is null || selectedAppId is null)
        {
            return;
        }

        var appId = selectedAppId;
        var installing = detail.Install is null;
        ShowResult(string.Empty, true);
        jobRunning = true;
        jobKind = installing ? "install" : "uninstall";
        jobAppId = appId;
        ShowProgress(null);
        UpdateActionState();
        var response = installing
            ? await client.InstallAsync(appId, selectedBuild ?? string.Empty, selectedQuality, selectedModel, Experimental)
            : await client.UninstallAsync(appId, Experimental);
        if (response.Status == UpscalersResponseStatus.Ok && response.Job is { } job)
        {
            ShowProgress(job);
            StartPolling();
            return;
        }

        if (response.ErrorCode == "busy" && response.Job is { State: UpscalerJobStates.Running } running)
        {
            await ResumeJobAsync(running);
            ShowResult(ErrorMessage("busy"), false);
            return;
        }

        jobRunning = false;
        HideProgress();
        ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        UpdateActionState();
    }

    private async Task ResumeJobAsync(UpscalerJobStatus job)
    {
        jobRunning = true;
        jobKind = job.Kind;
        jobAppId = job.AppId;
        if (selectedAppId != job.AppId)
        {
            selectedAppId = job.AppId;
            selectionGeneration++;
            detail = null;
        }

        ShowProgress(job);
        StartPolling();
        await LoadOverviewAsync();
        ShowProgress(job);
    }

    private void StartPolling()
    {
        pollFailures = 0;
        pollTimer.Start();
    }

    private async void PollTimer_Tick(object? sender, object args)
    {
        if (polling)
        {
            return;
        }

        polling = true;
        try
        {
            var response = await client.JobAsync();
            if (response.Status == UpscalersResponseStatus.Ok && response.Job is { } job && job.AppId == jobAppId)
            {
                pollFailures = 0;
                if (job.State == UpscalerJobStates.Running)
                {
                    ShowProgress(job);
                    return;
                }

                pollTimer.Stop();
                await FinishAsync(job);
                return;
            }

            if (++pollFailures >= MaximumPollFailures)
            {
                pollTimer.Stop();
                await FinishAsync(null);
            }
        }
        finally
        {
            polling = false;
        }
    }

    private async Task FinishAsync(UpscalerJobStatus? job)
    {
        var kind = jobKind;
        var appId = jobAppId;
        var message = job is null
            ? Localized("UpscalersUnconfirmed")
            : job.State == UpscalerJobStates.Error ? ErrorMessage(job.Error) : string.Empty;
        var good = false;
        if (job is { State: UpscalerJobStates.Done })
        {
            statusTitle.Text = kind == "install"
                ? string.Format(Localized("UpscalersStatusInstalled"), SelectedBadge())
                : Localized("UpscalersStatusNone");
            statusSub.Text = string.Empty;
        }

        ShowLoadingRow();
        if (selectedAppId == appId)
        {
            await LoadGameAsync();
        }

        jobRunning = false;
        HideProgress();
        if (job is { State: UpscalerJobStates.Done })
        {
            var confirmed = detail is not null && selectedAppId == appId;
            var installed = confirmed ? detail!.Install : null;
            if (!confirmed)
            {
                message = Localized("UpscalersUnconfirmed");
            }
            else if (kind == "install")
            {
                good = installed is not null && installed.Status == UpscalerGameStates.Installed;
                message = good
                    ? IsDll(installed!.Build)
                        ? string.Format(Localized("UpscalersInstalledDll"), DllLabel(installed.Build, installed.Label ?? string.Empty))
                        : string.Format(Localized("UpscalersInstalledOk"), installed.Label ?? string.Empty)
                    : Localized("UpscalersUnconfirmed");
            }
            else
            {
                good = installed is null;
                message = good ? Localized("UpscalersRemovedOk") : Localized("UpscalersUnconfirmed");
            }
        }

        ShowResult(message, good);
        RenderStatus();
        UpdateActionState();
        _ = RefreshOverviewQuietlyAsync();
    }

    private async Task RefreshOverviewQuietlyAsync()
    {
        if (refreshing)
        {
            return;
        }

        refreshing = true;
        try
        {
            await LoadOverviewAsync(reloadGame: false);
        }
        catch
        {
        }
        finally
        {
            refreshing = false;
        }
    }

    private void ShowLoadingRow()
    {
        progressText.Text = Localized("UpscalersLoading");
        progressPanel.Visibility = Visibility.Visible;
        progressBar.IsIndeterminate = true;
    }

    private void ClearResult()
    {
        if (resultText.Text.Length == 0)
        {
            return;
        }

        ShowResult(string.Empty, true);
        RenderStatus();
    }

    private void ShowResult(string text, bool good)
    {
        resultText.Text = text;
        resultText.Foreground = Resource<Brush>(good ? "PdcOkBrush" : "PdcWarnBrush");
    }

    private void ShowProgress(UpscalerJobStatus? job)
    {
        var stage = job?.Stage ?? "prepare";
        var total = job?.TotalBytes ?? 0;
        var done = job?.DoneBytes ?? 0;
        progressText.Text = stage switch
        {
            "download" when total > 0 => string.Format(Localized("UpscalersProgressDownload"), Megabytes(done), Megabytes(total)),
            "download" => Localized("UpscalersProgressDownloadStart"),
            "install" => Localized("UpscalersProgressInstall"),
            "python" => Localized("UpscalersProgressPython"),
            "unpack" => Localized("UpscalersProgressUnpack"),
            "restore" => Localized("UpscalersProgressRestore"),
            _ => Localized("UpscalersProgressPrepare"),
        };
        progressPanel.Visibility = Visibility.Visible;
        progressBar.IsIndeterminate = !(stage == "download" && total > 0);
        if (!progressBar.IsIndeterminate)
        {
            progressBar.Value = Math.Min(1.0, (double)done / total);
        }

        if (!progressShown)
        {
            progressShown = true;
            progressPanel.StartBringIntoView();
        }
    }

    private void HideProgress()
    {
        progressShown = false;
        progressText.Text = string.Empty;
        progressPanel.Visibility = Visibility.Collapsed;
        progressBar.IsIndeterminate = false;
    }

    private static string Megabytes(long bytes) =>
        (bytes / 1048576.0).ToString("0.#", System.Globalization.CultureInfo.CurrentCulture);

    private static string ErrorMessage(string? code)
    {
        var key = SettingsErrorKey(code) ?? code switch
        {
            "running" => "UpscalersErrRunning",
            "updating" => "UpscalersErrUpdating",
            "update_pending" => "UpscalersErrUpdatePending",
            "busy" => "UpscalersErrBusy",
            "anti_cheat" => "UpscalersErrAntiCheat",
            "protected_folder" => "UpscalersErrProtectedFolder",
            "foreign" => "UpscalersErrForeign",
            "recipe_unsupported" => "UpscalersErrRecipeUnsupported",
            "experimental_required" => "UpscalersErrExperimentalRequired",
            "download_failed" or "hash_mismatch" or "size_mismatch" or "unpack_failed" or "unsafe_archive" => "UpscalersErrDownload",
            "no_space" => "UpscalersErrNoSpace",
            "helixsr_no_fsr" => "UpscalersErrHelixNoFsr",
            "helixsr_failed" => "UpscalersErrHelixFailed",
            "helixsr_missing" => "UpscalersErrHelixMissing",
            "install_unverified" => "UpscalersErrInstallUnverified",
            "files_kept" => "UpscalersErrFilesKept",
            "no_exe" => "UpscalersErrNoExe",
            "no_builds" => "UpscalersErrNoBuilds",
            "upscalers_broker_launch_failed" or "upscalers_broker_unreachable" or "upscalers_response_unavailable" => "UpscalersErrCompanion",
            _ => "UpscalersErrGeneric",
        };
        return Localized(key);
    }

    private static Border Card(UIElement child) => new()
    {
        Padding = new Thickness(12),
        CornerRadius = Resource<CornerRadius>("PdcRadiusInset"),
        Background = Resource<Brush>("PdcLayerBrush"),
        Child = child,
    };

    private static Brush AccentFill()
    {
        var accent = ((SolidColorBrush)Resource<Brush>("PdcAccentBrush")).Color;
        return new SolidColorBrush(Color.FromArgb(0x70, accent.R, accent.G, accent.B));
    }

    private static TextBlock Muted(string text) => new()
    {
        Text = text,
        Style = Resource<Style>("PdcMutedStyle"),
        TextWrapping = TextWrapping.WrapWholeWords,
    };

    private static void CollapseWhenEmpty(TextBlock block)
    {
        void Update() => block.Visibility = string.IsNullOrEmpty(block.Text) ? Visibility.Collapsed : Visibility.Visible;
        block.RegisterPropertyChangedCallback(TextBlock.TextProperty, (_, _) => Update());
        Update();
    }

    private static T Resource<T>(string key) => (T)Application.Current.Resources[key];

    private static string Localized(string key) => Strings.GetString(key);
}
