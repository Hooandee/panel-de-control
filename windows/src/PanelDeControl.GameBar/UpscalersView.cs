using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using PanelDeControl.Core.Upscalers;
using Windows.ApplicationModel.Resources;
using Windows.UI;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Automation.Peers;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

/// <summary>
/// Escaladores on Windows, experimental: installed Steam games, the build and quality to install, and the real
/// outcome of the companion's install or removal job.
/// </summary>
public sealed class UpscalersView : UserControl
{
    private static readonly ResourceLoader Strings = ResourceLoader.GetForViewIndependentUse();
    private static readonly string[] Qualities = { "native", "quality", "balanced", "performance" };
    private const string DefaultQuality = "quality";
    private const int MaximumPollFailures = 12;

    private readonly UpscalersClient client = new();
    private readonly DispatcherTimer pollTimer = new() { Interval = TimeSpan.FromMilliseconds(500) };
    private readonly ToggleSwitch experimentalToggle = new();
    private readonly StackPanel content = new() { Spacing = 10, Visibility = Visibility.Collapsed };
    private readonly TextBlock gpuText = new();
    private readonly TextBlock statusText = new();
    private readonly StackPanel gameList = new() { Spacing = 4 };
    private readonly StackPanel detailPanel = new() { Spacing = 8, Visibility = Visibility.Collapsed };
    private readonly TextBlock detailTitle = new();
    private readonly TextBlock detailInfo = new();
    private readonly TextBlock recipeText = new();
    private readonly TextBlock installedText = new();
    private readonly TextBlock buildLabel = new();
    private readonly StackPanel buildList = new() { Spacing = 4 };
    private readonly TextBlock qualityLabel = new();
    private readonly Grid qualityRow = new() { ColumnSpacing = 4 };
    private readonly Border qualityHost;
    private readonly TextBlock hintText = new();
    private readonly Button actionButton = new();
    private readonly ProgressBar progressBar = new() { Minimum = 0, Maximum = 1, Visibility = Visibility.Collapsed };
    private readonly TextBlock progressText = new();
    private readonly TextBlock resultText = new();

    private UpscalerGameSummary[] games = Array.Empty<UpscalerGameSummary>();
    private UpscalerGameDetail? detail;
    private string? selectedAppId;
    private string? selectedBuild;
    private string selectedQuality = DefaultQuality;
    private bool refreshing;
    private bool loadingGame;
    private bool jobRunning;
    private bool polling;
    private int pollFailures;
    private string jobKind = "";
    private string jobAppId = "";
    private long selectionGeneration;

    public UpscalersView()
    {
        var title = new TextBlock { Style = Resource<Style>("PdcTitleStyle"), VerticalAlignment = VerticalAlignment.Center, Text = Localized("UpscalersTitle") };
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
        header.Children.Add(title);
        Grid.SetColumn(experimentalToggle, 1);
        header.Children.Add(experimentalToggle);

        var intro = Muted(Localized("UpscalersIntro"));
        intro.Margin = new Thickness(0, 4, 0, 0);

        gpuText.Style = Resource<Style>("PdcCaptionStyle");
        statusText.Style = Resource<Style>("PdcMutedStyle");
        statusText.TextWrapping = TextWrapping.WrapWholeWords;
        detailTitle.Style = Resource<Style>("PdcTitleStyle");
        detailTitle.TextWrapping = TextWrapping.WrapWholeWords;
        foreach (var line in new[] { detailInfo, recipeText, installedText, hintText, progressText })
        {
            line.Style = Resource<Style>("PdcCaptionStyle");
            line.TextWrapping = TextWrapping.WrapWholeWords;
        }

        hintText.Foreground = Resource<Brush>("PdcWarnBrush");
        buildLabel.Style = Resource<Style>("PdcBodyStyle");
        buildLabel.Text = Localized("UpscalersBuildLabel");
        qualityLabel.Style = Resource<Style>("PdcBodyStyle");
        qualityLabel.Text = Localized("UpscalersQualityLabel");
        resultText.Style = Resource<Style>("PdcCaptionStyle");
        resultText.TextWrapping = TextWrapping.WrapWholeWords;
        AutomationProperties.SetLiveSetting(resultText, AutomationLiveSetting.Polite);
        AutomationProperties.SetLiveSetting(progressText, AutomationLiveSetting.Polite);
        progressBar.Foreground = Resource<Brush>("PdcAccentBrush");

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

        actionButton.Style = Resource<Style>("PdcChipButtonStyle");
        actionButton.Padding = new Thickness(14, 9, 14, 9);
        actionButton.HorizontalAlignment = HorizontalAlignment.Left;
        actionButton.Click += ActionButton_Click;

        detailPanel.Children.Add(detailTitle);
        detailPanel.Children.Add(detailInfo);
        detailPanel.Children.Add(recipeText);
        detailPanel.Children.Add(installedText);
        detailPanel.Children.Add(buildLabel);
        detailPanel.Children.Add(buildList);
        detailPanel.Children.Add(qualityLabel);
        detailPanel.Children.Add(qualityHost);
        detailPanel.Children.Add(hintText);
        detailPanel.Children.Add(actionButton);

        content.Children.Add(gpuText);
        content.Children.Add(statusText);
        content.Children.Add(gameList);
        content.Children.Add(detailPanel);
        content.Children.Add(progressBar);
        content.Children.Add(progressText);
        content.Children.Add(resultText);
        foreach (var line in new[] { gpuText, statusText, hintText, progressText, resultText, detailInfo, recipeText, installedText })
        {
            CollapseWhenEmpty(line);
        }

        var stack = new StackPanel { Children = { header, intro, new Border { Margin = new Thickness(0, 12, 0, 0), Child = content } } };
        Content = new Border { Style = Resource<Style>("PdcCardStyle"), Child = stack };

        pollTimer.Tick += PollTimer_Tick;
        Unloaded += (_, _) => pollTimer.Stop();
    }

    private bool Experimental => experimentalToggle.IsOn;

    public async Task RefreshAsync()
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
                ResumeJob(running);
                return;
            }

            await LoadOverviewAsync();
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
            resultText.Text = string.Empty;
        }
    }

    private async Task LoadOverviewAsync()
    {
        var response = await client.OverviewAsync();
        if (!Experimental)
        {
            return;
        }

        if (response.Status != UpscalersResponseStatus.Ok || response.Overview is null)
        {
            games = Array.Empty<UpscalerGameSummary>();
            gpuText.Text = string.Empty;
            statusText.Text = ErrorMessage(response.ErrorCode);
            RenderGames();
            return;
        }

        var overview = response.Overview;
        games = overview.Games.OrderBy(game => game.Name, StringComparer.CurrentCultureIgnoreCase).ToArray();
        var family = overview.Gpu == "unknown" ? Localized("UpscalersGpuUnknown") : overview.Gpu;
        gpuText.Text = string.Format(Localized("UpscalersGpu"), family);
        statusText.Text = !overview.SteamFound
            ? Localized("UpscalersNoSteam")
            : games.Length == 0 ? Localized("UpscalersNoGames") : string.Empty;
        if (selectedAppId is not null && games.All(game => game.AppId != selectedAppId))
        {
            selectedAppId = null;
            detail = null;
        }

        RenderGames();
        if (selectedAppId is not null)
        {
            await LoadGameAsync();
        }
        else
        {
            RenderDetail();
        }
    }

    private void RenderGames()
    {
        gameList.Children.Clear();
        foreach (var game in games)
        {
            var selected = game.AppId == selectedAppId;
            var text = new StackPanel();
            text.Children.Add(new TextBlock { Text = game.Name, Style = Resource<Style>("PdcBodyStyle"), TextTrimming = TextTrimming.CharacterEllipsis });
            var state = GameState(game);
            if (state.Length > 0)
            {
                text.Children.Add(new TextBlock { Text = state, Style = Resource<Style>("PdcCaptionStyle"), TextWrapping = TextWrapping.WrapWholeWords });
            }

            var button = new Button
            {
                Tag = game.AppId,
                Content = text,
                Style = Resource<Style>("PdcChipButtonStyle"),
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Padding = new Thickness(12, 8, 12, 8),
                IsEnabled = !jobRunning,
                Background = selected ? AccentFill() : Resource<Brush>("PdcLayerBrush"),
            };
            AutomationProperties.SetName(button, game.Name + (state.Length > 0 ? ". " + state : string.Empty));
            button.Click += GameButton_Click;
            gameList.Children.Add(button);
        }
    }

    private static string GameState(UpscalerGameSummary game)
    {
        var parts = new List<string>();
        switch (game.State)
        {
            case UpscalerGameStates.Installed:
                var version = Join(game.Build, game.Version);
                parts.Add(version.Length > 0 ? string.Format(Localized("UpscalersStateInstalledBuild"), version) : Localized("UpscalersStateInstalled"));
                break;
            case UpscalerGameStates.Missing:
                parts.Add(Localized("UpscalersStateMissing"));
                break;
            case UpscalerGameStates.Foreign:
                parts.Add(Localized("UpscalersStateForeign"));
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

    private static string Join(string? build, string? version) =>
        string.Join(" ", new[] { build, version }.Where(part => !string.IsNullOrEmpty(part)));

    private async void GameButton_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: string appId })
        {
            return;
        }

        selectedAppId = appId;
        selectionGeneration++;
        detail = null;
        resultText.Text = string.Empty;
        RenderGames();
        RenderDetail();
        await LoadGameAsync();
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
        RenderDetail();
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
            if (installed?.Quality is { } quality && Qualities.Contains(quality))
            {
                selectedQuality = quality;
            }
        }
        else
        {
            detail = null;
            resultText.Text = ErrorMessage(response.ErrorCode);
        }

        RenderDetail();
    }

    private void RenderDetail()
    {
        if (selectedAppId is null)
        {
            detailPanel.Visibility = Visibility.Collapsed;
            return;
        }

        detailPanel.Visibility = Visibility.Visible;
        var summary = games.FirstOrDefault(game => game.AppId == selectedAppId);
        detailTitle.Text = summary?.Name ?? string.Empty;
        var showControls = detail is not null;
        actionButton.Visibility = showControls ? Visibility.Visible : Visibility.Collapsed;
        if (detail is null)
        {
            foreach (var element in new UIElement[] { buildLabel, buildList, qualityLabel, qualityHost })
            {
                element.Visibility = Visibility.Collapsed;
            }

            detailInfo.Text = loadingGame ? Localized("UpscalersLoading") : string.Empty;
            recipeText.Text = string.Empty;
            installedText.Text = string.Empty;
            hintText.Text = string.Empty;
            return;
        }

        var installed = detail.Install;
        var info = new List<string>();
        if (!string.IsNullOrEmpty(detail.Exe))
        {
            info.Add(detail.Exe!);
        }

        if (detail.Apis.Length > 0)
        {
            info.Add(string.Join(", ", detail.Apis));
        }

        detailInfo.Text = string.Join(" · ", info);
        recipeText.Text = detail.Recipe is null
            ? Localized("UpscalersRecipeNone")
            : !detail.Recipe.Installable
                ? Localized("UpscalersRecipeUnsupported")
                : detail.Recipe.Status == "verified" ? Localized("UpscalersRecipeVerified") : Localized("UpscalersRecipeExperimental");
        installedText.Text = installed is null
            ? string.Empty
            : string.Format(
                Localized("UpscalersInstalledInfo"),
                Join(installed.Build, installed.Version)
                + (installed.Status == UpscalerGameStates.Missing ? " · " + Localized("UpscalersStateMissing") : string.Empty));

        var choosing = installed is null;
        var choice = choosing ? Visibility.Visible : Visibility.Collapsed;
        buildLabel.Visibility = choice;
        buildList.Visibility = choice;
        qualityLabel.Visibility = choice;
        qualityHost.Visibility = choice;
        RenderBuilds();
        UpdateActionState();
    }

    private void RenderBuilds()
    {
        buildList.Children.Clear();
        if (detail is null)
        {
            return;
        }

        foreach (var build in detail.Builds)
        {
            var label = $"{FamilyName(build.Family)} {build.Version}";
            if (build.DownloadBytes > 0)
            {
                label += " · " + string.Format(Localized("UpscalersMegabytes"), Megabytes(build.DownloadBytes));
            }

            if (build.Id == detail.Preferred)
            {
                label += " · " + Localized("UpscalersRecommended");
            }

            if (!build.Supported)
            {
                label += " · " + Localized("UpscalersUntested");
            }

            var chip = new Button
            {
                Tag = build.Id,
                Content = label,
                Style = Resource<Style>("PdcChipButtonStyle"),
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Padding = new Thickness(12, 8, 12, 8),
            };
            chip.Click += BuildChip_Click;
            buildList.Children.Add(chip);
        }
    }

    private static string FamilyName(string family) => family switch
    {
        "fsr" => "FSR",
        "xess" => "XeSS",
        "dlss" => "DLSS",
        _ => family,
    };

    private void BuildChip_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: string build })
        {
            return;
        }

        selectedBuild = build;
        UpdateActionState();
    }

    private void QualityChip_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || sender is not Button { Tag: string quality })
        {
            return;
        }

        selectedQuality = quality;
        UpdateActionState();
    }

    private void UpdateActionState()
    {
        foreach (var chip in buildList.Children.OfType<Button>())
        {
            var active = Equals(chip.Tag, selectedBuild);
            chip.Background = active ? AccentFill() : Resource<Brush>("PdcLayerBrush");
            chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
            chip.IsEnabled = !jobRunning;
        }

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
        string? reason = null;
        if (detail is not null)
        {
            var summary = detail.Game;
            var installed = detail.Install is not null;
            actionButton.Content = Localized(installed ? "UpscalersRemove" : "UpscalersInstall");
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

        hintText.Text = !jobRunning && reason is not null ? ErrorMessage(reason) : string.Empty;
        actionButton.IsEnabled = detail is not null && !jobRunning && !loadingGame && reason is null;
    }

    private async void ActionButton_Click(object sender, RoutedEventArgs args)
    {
        if (jobRunning || detail is null || selectedAppId is null)
        {
            return;
        }

        var appId = selectedAppId;
        var installing = detail.Install is null;
        resultText.Text = string.Empty;
        jobRunning = true;
        jobKind = installing ? "install" : "uninstall";
        jobAppId = appId;
        ShowProgress(null);
        UpdateActionState();
        var response = installing
            ? await client.InstallAsync(appId, selectedBuild ?? string.Empty, selectedQuality, null, Experimental)
            : await client.UninstallAsync(appId, Experimental);
        if (response.Status == UpscalersResponseStatus.Ok && response.Job is { } job)
        {
            ShowProgress(job);
            StartPolling();
            return;
        }

        if (response.ErrorCode == "busy" && response.Job is { State: UpscalerJobStates.Running } running)
        {
            ResumeJob(running);
            resultText.Text = ErrorMessage("busy");
            return;
        }

        jobRunning = false;
        HideProgress();
        resultText.Text = ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable");
        UpdateActionState();
    }

    private void ResumeJob(UpscalerJobStatus job)
    {
        jobRunning = true;
        jobKind = job.Kind;
        jobAppId = job.AppId;
        RenderGames();
        UpdateActionState();
        ShowProgress(job);
        StartPolling();
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
        HideProgress();
        var message = job is null
            ? Localized("UpscalersUnconfirmed")
            : job.State == UpscalerJobStates.Error ? ErrorMessage(job.Error) : string.Empty;
        jobRunning = false;
        await LoadOverviewAsync();
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
                message = installed is not null && installed.Status == UpscalerGameStates.Installed
                    ? string.Format(Localized("UpscalersInstalledOk"), Join(installed.Build, installed.Version))
                    : Localized("UpscalersUnconfirmed");
            }
            else
            {
                message = installed is null ? Localized("UpscalersRemovedOk") : Localized("UpscalersUnconfirmed");
            }
        }

        resultText.Text = message;
        UpdateActionState();
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
            "restore" => Localized("UpscalersProgressRestore"),
            _ => Localized("UpscalersProgressPrepare"),
        };
        progressBar.Visibility = Visibility.Visible;
        progressBar.IsIndeterminate = !(stage == "download" && total > 0);
        if (!progressBar.IsIndeterminate)
        {
            progressBar.Value = Math.Min(1.0, (double)done / total);
        }
    }

    private void HideProgress()
    {
        progressText.Text = string.Empty;
        progressBar.Visibility = Visibility.Collapsed;
        progressBar.IsIndeterminate = false;
    }

    private static string Megabytes(long bytes) =>
        (bytes / 1048576.0).ToString("0.#", System.Globalization.CultureInfo.CurrentCulture);

    private static string ErrorMessage(string? code)
    {
        var key = code switch
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
            "install_unverified" => "UpscalersErrInstallUnverified",
            "files_kept" => "UpscalersErrFilesKept",
            "no_exe" => "UpscalersErrNoExe",
            "no_builds" => "UpscalersErrNoBuilds",
            "upscalers_broker_launch_failed" or "upscalers_broker_unreachable" or "upscalers_response_unavailable" => "UpscalersErrCompanion",
            _ => "UpscalersErrGeneric",
        };
        return Localized(key);
    }

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
