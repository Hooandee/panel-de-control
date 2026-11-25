using System.Linq;
using PanelDeControl.Core.Upscalers;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;

namespace PanelDeControl.GameBar;

/// <summary>Games that need a hand: checking the install now, cancelling a job and choosing the executable.</summary>
public sealed partial class UpscalersView
{
    private readonly Button verifyButton = new();
    private readonly Button cancelButton = new();
    private readonly StackPanel exePanel = new() { Spacing = 6 };
    private readonly TextBox exeBox = new();
    private readonly Button exeSaveButton = new();
    private readonly Button exeAutoButton = new();
    private bool gameBusy;

    private UIElement BuildVerifyButton()
    {
        Prepare(verifyButton, "UpscalersVerify", VerifyButton_Click);
        return verifyButton;
    }

    private UIElement BuildCancelButton()
    {
        Prepare(cancelButton, "UpscalersCancel", CancelButton_Click);
        return cancelButton;
    }

    private UIElement BuildExeEditor()
    {
        var title = new TextBlock { Style = Resource<Style>("PdcBodyStyle"), FontWeight = FontWeights.SemiBold, Text = Localized("UpscalersExeLabel") };
        Prepare(exeSaveButton, "UpscalersExeSave", (_, _) => SetExe(exeBox.Text.Trim()));
        Prepare(exeAutoButton, "UpscalersExeAuto", (_, _) => SetExe(null));
        exePanel.Children.Add(title);
        exePanel.Children.Add(exeBox);
        exePanel.Children.Add(exeSaveButton);
        exePanel.Children.Add(exeAutoButton);
        return exePanel;
    }

    private void RenderGameExtras()
    {
        var idle = !gameBusy && !settingsBusy && !jobRunning && !loadingGame;
        verifyButton.Visibility = detail?.Install is { Build.Length: > 0 } ? Visibility.Visible : Visibility.Collapsed;
        verifyButton.IsEnabled = idle;
        cancelButton.Visibility = jobRunning ? Visibility.Visible : Visibility.Collapsed;
        cancelButton.IsEnabled = jobRunning;
        exePanel.Visibility = detail is not null ? Visibility.Visible : Visibility.Collapsed;
        exeSaveButton.IsEnabled = idle && exeBox.Text.Trim().Length > 0;
        exeAutoButton.IsEnabled = idle;
        if (detail?.Exe is { } exe && FocusState.Unfocused == exeBox.FocusState && exeBox.Text != exe)
        {
            exeBox.Text = exe;
        }
    }

    private async void VerifyButton_Click(object sender, RoutedEventArgs args)
    {
        if (selectedAppId is not { } appId || gameBusy)
        {
            return;
        }

        gameBusy = true;
        UpdateActionState();
        var response = await client.VerifyAsync(appId);
        gameBusy = false;
        if (appId != selectedAppId)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Verify is { } verdict)
        {
            if (detail?.Install is { } install)
            {
                install.Verdict = verdict.Result;
                install.Observed = verdict.Observed;
                install.Provider = verdict.Provider;
                RenderStatus();
            }

            var text = Localized("UpscalersVerdict_" + verdict.Result);
            var seen = new[] { verdict.Observed, verdict.Provider }.Where(part => !string.IsNullOrEmpty(part)).ToArray();
            ShowResult(seen.Length > 0 ? text + " · " + string.Join(" · ", seen) : text, verdict.Result == "active");
        }
        else
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        }

        UpdateActionState();
    }

    private async void CancelButton_Click(object sender, RoutedEventArgs args)
    {
        cancelButton.IsEnabled = false;
        var response = await client.CancelAsync(Experimental);
        if (response.Status != UpscalersResponseStatus.Ok)
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        }
    }

    private async void SetExe(string? exe)
    {
        if (selectedAppId is not { } appId || gameBusy)
        {
            return;
        }

        gameBusy = true;
        UpdateActionState();
        var response = await client.SetExeAsync(appId, exe, Experimental);
        gameBusy = false;
        if (appId != selectedAppId)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Game is { } game)
        {
            detail = game;
            exeBox.Text = game.Exe ?? string.Empty;
            ShowResult(Localized("UpscalersApplied"), true);
            RenderView();
        }
        else
        {
            ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
            UpdateActionState();
        }
    }
}
