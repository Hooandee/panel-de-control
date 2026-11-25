using System;
using System.Linq;
using System.Threading.Tasks;
using PanelDeControl.Core.Upscalers;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;

namespace PanelDeControl.GameBar;

/// <summary>
/// Changing an install without reinstalling: quality and frame generation (<c>configure</c>), the image controls'
/// sharpness and HelixSR INT8, and single OptiScaler.ini keys from the advanced editor.
/// </summary>
public sealed partial class UpscalersView
{
    private static readonly string[] Routes = { "game", "optiscaler", "anr" };
    private readonly StackPanel settingsPanel = new() { Spacing = 8, Visibility = Visibility.Collapsed };
    private readonly ToggleSwitch frameGenToggle = new();
    private readonly Grid routeRow = new() { ColumnSpacing = 4 };
    private readonly Button applyButton = new();
    private readonly StackPanel imagePanel = new() { Spacing = 6, Visibility = Visibility.Collapsed };
    private readonly ToggleSwitch sharpnessToggle = new();
    private readonly Slider sharpnessSlider = new() { Minimum = 0, Maximum = 100, StepFrequency = 1 };
    private readonly ComboBox int8Box = new() { ItemsSource = new[] { "auto", "on", "off" }, HorizontalAlignment = HorizontalAlignment.Stretch };
    private readonly Button imageApplyButton = new();
    private readonly Button imageRestoreButton = new();
    private readonly StackPanel iniPanel = new() { Spacing = 6, Visibility = Visibility.Collapsed };
    private readonly TextBox iniKeyBox = new();
    private readonly TextBox iniValueBox = new();
    private readonly TextBlock iniHint = new();
    private readonly Button iniSaveButton = new();
    private UpscalerImageSettings? image;
    private UpscalerIniSection[]? iniSchema;
    // Null keeps the planner's own route, as Linux does until the user picks one.
    private string? selectedRoute;
    private (bool On, double Value)? loadedSharpness;
    private string? loadedInt8;
    private bool frameGenOn;
    private bool settingsBusy;

    private UIElement BuildSettingsPanel()
    {
        var title = new TextBlock { Style = Resource<Style>("PdcBodyStyle"), FontWeight = FontWeights.SemiBold, Text = Localized("UpscalersSettingsTitle") };
        frameGenToggle.Header = Localized("UpscalersFrameGen");
        frameGenToggle.Toggled += (_, _) =>
        {
            frameGenOn = frameGenToggle.IsOn;
            RenderSettings();
        };
        for (var index = 0; index < Routes.Length; index++)
        {
            routeRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var chip = new Button { Tag = Routes[index], Content = Localized("UpscalersRoute_" + Routes[index]), Style = Resource<Style>("PdcSegmentButtonStyle") };
            chip.Click += (sender, _) =>
            {
                selectedRoute = (string)((Button)sender).Tag;
                RenderSettings();
            };
            Grid.SetColumn(chip, index);
            routeRow.Children.Add(chip);
        }

        Prepare(applyButton, "UpscalersApply", ApplyButton_Click);

        sharpnessToggle.Header = Localized("UpscalersSharpness");
        sharpnessSlider.Style = Resource<Style>("PdcSliderStyle");
        AutomationProperties.SetName(sharpnessSlider, Localized("UpscalersSharpness"));
        int8Box.Header = Localized("UpscalersInt8");
        Prepare(imageApplyButton, "UpscalersSharpnessApply", ImageApplyButton_Click);
        Prepare(imageRestoreButton, "UpscalersRestore", ImageRestoreButton_Click);
        imagePanel.Children.Add(sharpnessToggle);
        imagePanel.Children.Add(sharpnessSlider);
        imagePanel.Children.Add(int8Box);
        imagePanel.Children.Add(imageApplyButton);
        imagePanel.Children.Add(imageRestoreButton);

        settingsPanel.Children.Add(title);
        settingsPanel.Children.Add(frameGenToggle);
        settingsPanel.Children.Add(routeRow);
        settingsPanel.Children.Add(applyButton);
        settingsPanel.Children.Add(imagePanel);
        return Card(settingsPanel);
    }

    private UIElement BuildIniEditor()
    {
        var title = new TextBlock { Style = Resource<Style>("PdcBodyStyle"), FontWeight = FontWeights.SemiBold, Text = Localized("UpscalersIniTitle") };
        iniKeyBox.Header = Localized("UpscalersIniKey");
        iniKeyBox.TextChanged += (_, _) => RenderIniHint();
        iniValueBox.Header = Localized("UpscalersIniValue");
        iniHint.Style = Resource<Style>("PdcCaptionStyle");
        iniHint.TextWrapping = TextWrapping.WrapWholeWords;
        CollapseWhenEmpty(iniHint);
        Prepare(iniSaveButton, "UpscalersIniSave", IniSaveButton_Click);
        iniPanel.Children.Add(title);
        iniPanel.Children.Add(iniKeyBox);
        iniPanel.Children.Add(iniHint);
        iniPanel.Children.Add(iniValueBox);
        iniPanel.Children.Add(iniSaveButton);
        return iniPanel;
    }

    private static void Prepare(Button button, string text, RoutedEventHandler click)
    {
        button.Style = Resource<Style>("PdcChipButtonStyle");
        button.Padding = new Thickness(12, 8, 12, 8);
        button.HorizontalAlignment = HorizontalAlignment.Stretch;
        button.HorizontalContentAlignment = HorizontalAlignment.Center;
        button.Content = Localized(text);
        button.Click += click;
    }

    private bool OptiScalerInstalled => detail?.Install is { Engine: "optiscaler", Status: UpscalerGameStates.Installed };

    private async Task LoadSettingsAsync(string appId, long generation)
    {
        var installed = detail?.Install;
        frameGenOn = installed?.FrameGen == true;
        selectedRoute = installed?.FrameGenRoute;
        image = null;
        iniSchema = null;
        RenderSettings();
        var response = await client.ImageAsync(appId);
        if (generation != selectionGeneration || appId != selectedAppId)
        {
            return;
        }

        ShowImage(response.Status == UpscalersResponseStatus.Ok ? response.Image : null);
        RenderSettings();
        if (advancedOpen)
        {
            await LoadIniAsync();
        }
    }

    private void ShowImage(UpscalerImageSettings? settings)
    {
        image = settings;
        loadedSharpness = null;
        if (settings?.Sharpness is { } sharpness)
        {
            sharpnessToggle.IsOn = sharpness.Enabled == true;
            sharpnessSlider.Value = Math.Round((sharpness.Value ?? 0) * 100);
            loadedSharpness = (sharpnessToggle.IsOn, sharpnessSlider.Value);
        }

        int8Box.SelectedItem = settings?.Int8;
        loadedInt8 = int8Box.SelectedItem as string;
    }

    private async Task LoadIniAsync()
    {
        var appId = selectedAppId;
        if (appId is null || !OptiScalerInstalled || iniSchema is not null)
        {
            RenderSettings();
            return;
        }

        var generation = selectionGeneration;
        var response = await client.IniAsync(appId);
        if (generation != selectionGeneration || appId != selectedAppId)
        {
            return;
        }

        iniSchema = response.Status == UpscalersResponseStatus.Ok ? response.Ini : null;
        RenderSettings();
    }

    private void ResetSettings()
    {
        image = null;
        iniSchema = null;
        settingsBusy = false;
        UpdateActionState();
        RenderSettings();
    }

    private void RenderSettings()
    {
        var install = detail?.Install;
        var configurable = install is { Status: UpscalerGameStates.Installed, Engine: "optiscaler" or "helixsr" } && !loadingGame;
        settingsPanel.Visibility = configurable || image?.Supported == true ? Visibility.Visible : Visibility.Collapsed;
        var optiScaler = install?.Engine == "optiscaler" && configurable;
        frameGenToggle.Visibility = optiScaler ? Visibility.Visible : Visibility.Collapsed;
        routeRow.Visibility = optiScaler && frameGenOn ? Visibility.Visible : Visibility.Collapsed;
        applyButton.Visibility = configurable ? Visibility.Visible : Visibility.Collapsed;
        if (frameGenToggle.IsOn != frameGenOn)
        {
            frameGenToggle.IsOn = frameGenOn;
        }

        foreach (var chip in routeRow.Children.OfType<Button>())
        {
            // ANR's files only go in with an install, so its route is offered only where they are.
            chip.Visibility = Equals(chip.Tag, "anr") && install?.Anr != true ? Visibility.Collapsed : Visibility.Visible;
            var active = Equals(chip.Tag, selectedRoute);
            chip.Background = active ? AccentFill() : Resource<Brush>("PdcLayerBrush");
            chip.FontWeight = active ? FontWeights.SemiBold : FontWeights.Normal;
        }

        var idle = !settingsBusy && !jobRunning;
        applyButton.IsEnabled = idle && configurable && Changed(install!);
        imagePanel.Visibility = image?.Supported == true ? Visibility.Visible : Visibility.Collapsed;
        var hasSharpness = image?.Sharpness is not null;
        sharpnessToggle.Visibility = hasSharpness ? Visibility.Visible : Visibility.Collapsed;
        sharpnessSlider.Visibility = hasSharpness ? Visibility.Visible : Visibility.Collapsed;
        int8Box.Visibility = image?.Int8 is not null ? Visibility.Visible : Visibility.Collapsed;
        imageApplyButton.IsEnabled = idle;
        imageRestoreButton.Visibility = image?.Managed == true ? Visibility.Visible : Visibility.Collapsed;
        imageRestoreButton.IsEnabled = idle;
        iniPanel.Visibility = OptiScalerInstalled && iniSchema is not null ? Visibility.Visible : Visibility.Collapsed;
        iniSaveButton.IsEnabled = idle;
        if (settingsBusy)
        {
            actionButton.IsEnabled = false;
        }
    }

    private string? ChosenQuality(UpscalerInstallEntry install) => selectedQuality.Length == 0 ? install.Quality : selectedQuality;

    private bool Changed(UpscalerInstallEntry install) =>
        install.Engine == "optiscaler"
            ? ChosenQuality(install) != install.Quality || frameGenOn != (install.FrameGen == true) || (frameGenOn && selectedRoute != install.FrameGenRoute)
            : ChosenQuality(install) != install.Quality;

    private void RenderIniHint()
    {
        var typed = iniKeyBox.Text.Trim();
        var dot = typed.IndexOf('.');
        var match = iniSchema?
            .Where(section => dot < 0 || string.Equals(section.Name, typed.Substring(0, dot), StringComparison.Ordinal))
            .SelectMany(section => section.Keys.Select(key => (Section: section.Name, Key: key)))
            .Where(entry => string.Equals(entry.Key.Key, dot < 0 ? typed : typed.Substring(dot + 1), StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (match is not { Count: 1 })
        {
            iniHint.Text = string.Empty;
            return;
        }

        var (section, key) = match[0];
        var parts = new[]
        {
            section + "." + key.Key + " = " + key.Value + (key.Managed ? "  ·  " + Localized("UpscalersIniManaged") : string.Empty),
            key.Choices is { Length: > 0 } ? string.Join(", ", key.Choices) : null,
            key.Help.FirstOrDefault(),
        };
        iniHint.Text = string.Join("\n", parts.Where(part => !string.IsNullOrEmpty(part)));
    }

    private async void ApplyButton_Click(object sender, RoutedEventArgs args)
    {
        if (detail?.Install is not { } install || selectedAppId is not { } appId || settingsBusy)
        {
            return;
        }

        settingsBusy = true;
        RenderSettings();
        var response = await client.ConfigureAsync(appId, ChosenQuality(install), install.Sharpness,
            install.Engine == "optiscaler" && frameGenOn, frameGenOn ? selectedRoute : install.FrameGenRoute, install.Model, Experimental);
        settingsBusy = false;
        UpdateActionState();
        if (appId != selectedAppId)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Options is { } options)
        {
            install.Quality = options.Quality;
            selectedQuality = options.Quality is { } saved && Qualities.Contains(saved) ? saved : string.Empty;
            install.FrameGen = options.FrameGen == "on" ? true : null;
            install.FrameGenRoute = options.FrameGenRoute;
            ShowResult(Localized(options.Live == false ? "UpscalersAppliedNextLaunch" : "UpscalersApplied"), true);
        }
        else
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        }

        RenderSettings();
    }

    private async void ImageApplyButton_Click(object sender, RoutedEventArgs args)
    {
        if (selectedAppId is not { } appId || image is null || settingsBusy)
        {
            return;
        }

        settingsBusy = true;
        RenderSettings();
        var sharpness = image.Sharpness is not null && loadedSharpness != (sharpnessToggle.IsOn, sharpnessSlider.Value);
        var value = Math.Round(sharpnessSlider.Value) / 100.0;
        var int8 = image.Int8 is not null && int8Box.SelectedItem is string chosen && chosen != loadedInt8 ? chosen : null;
        if (!sharpness && int8 is null)
        {
            settingsBusy = false;
        UpdateActionState();
            RenderSettings();
            return;
        }

        var response = await client.SetImageAsync(appId, sharpness ? sharpnessToggle.IsOn : null, sharpness ? value : null, int8, Experimental);
        await FinishImageAsync(appId, response);
    }

    private async void ImageRestoreButton_Click(object sender, RoutedEventArgs args)
    {
        if (selectedAppId is not { } appId || settingsBusy)
        {
            return;
        }

        settingsBusy = true;
        RenderSettings();
        await FinishImageAsync(appId, await client.RestoreImageAsync(appId, Experimental));
    }

    private Task FinishImageAsync(string appId, UpscalersResponse response)
    {
        settingsBusy = false;
        UpdateActionState();
        if (appId != selectedAppId)
        {
            return Task.CompletedTask;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Image is { } updated)
        {
            ShowImage(updated);
            iniSchema = null;
            ShowResult(Localized("UpscalersApplied"), true);
        }
        else
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        }

        RenderSettings();
        return advancedOpen ? LoadIniAsync() : Task.CompletedTask;
    }

    private async void IniSaveButton_Click(object sender, RoutedEventArgs args)
    {
        var key = iniKeyBox.Text.Trim();
        var value = iniValueBox.Text.Trim();
        if (selectedAppId is not { } appId || settingsBusy || key.Length == 0 || value.Length == 0)
        {
            return;
        }

        settingsBusy = true;
        RenderSettings();
        var response = await client.SetIniAsync(appId, key, value, Experimental);
        settingsBusy = false;
        UpdateActionState();
        if (appId != selectedAppId)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.IniEdit is { } edit)
        {
            ShowResult(Localized("UpscalersIniSaved") + ": " + edit.Key + " = " + edit.Value, true);
            iniSchema = null;
            await LoadIniAsync();
            RenderIniHint();
        }
        else
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
            RenderSettings();
        }
    }

    private static string? SettingsErrorKey(string? code) => code switch
    {
        "ini_managed" => "UpscalersErrIniManaged",
        "ini_key" => "UpscalersErrIniKey",
        "ini_value" or "image_settings_value" => "UpscalersErrIniValue",
        "anr_reinstall" => "UpscalersErrAnrReinstall",
        "fg_route_unavailable" => "UpscalersErrFgRoute",
        "ini_changed" or "image_settings_changed" => "UpscalersErrIniChanged",
        _ => null,
    };
}
