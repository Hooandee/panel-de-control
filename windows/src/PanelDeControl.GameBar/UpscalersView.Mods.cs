using System.Linq;
using PanelDeControl.Core.Upscalers;
using Windows.UI.Text;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;

namespace PanelDeControl.GameBar;

/// <summary>Files the user brings: a game mod and the files a recipe cannot download, picked from Downloads or by path.</summary>
public sealed partial class UpscalersView
{
    private readonly StackPanel sourcesPanel = new() { Spacing = 6 };
    private readonly TextBlock modStatus = new();
    private readonly StackPanel candidateList = new() { Spacing = 4 };
    private readonly TextBox sourcePathBox = new();
    private readonly PasswordBox passwordBox = new() { Visibility = Visibility.Collapsed };
    private readonly Button addModButton = new();
    private readonly Button removeModButton = new();
    private readonly StackPanel dependencyButtons = new() { Spacing = 4 };
    private string? sourcesAppId;

    private UIElement BuildSourcesEditor()
    {
        var title = new TextBlock { Style = Resource<Style>("PdcBodyStyle"), FontWeight = FontWeights.SemiBold, Text = Localized("UpscalersSourcesTitle") };
        modStatus.Style = Resource<Style>("PdcCaptionStyle");
        modStatus.TextWrapping = TextWrapping.WrapWholeWords;
        CollapseWhenEmpty(modStatus);
        sourcePathBox.Header = Localized("UpscalersSourcePath");
        sourcePathBox.TextChanged += (_, _) => UpdateActionState();
        passwordBox.Header = Localized("UpscalersModPassword");
        Prepare(addModButton, "UpscalersModAdd", (_, _) => AddMod());
        Prepare(removeModButton, "UpscalersModRemove", (_, _) => SourceCall(client.RemoveModAsync(selectedAppId!, Experimental)));
        sourcesPanel.Children.Add(title);
        sourcesPanel.Children.Add(modStatus);
        sourcesPanel.Children.Add(candidateList);
        sourcesPanel.Children.Add(sourcePathBox);
        sourcesPanel.Children.Add(passwordBox);
        sourcesPanel.Children.Add(addModButton);
        sourcesPanel.Children.Add(removeModButton);
        sourcesPanel.Children.Add(dependencyButtons);
        return sourcesPanel;
    }

    private void RenderSources()
    {
        var idle = !gameBusy && !settingsBusy && !jobRunning && !loadingGame;
        sourcesPanel.Visibility = detail is not null && advancedOpen ? Visibility.Visible : Visibility.Collapsed;
        var mod = detail?.Mod is { Removed: not true } stored ? stored : null;
        modStatus.Text = mod is null
            ? detail?.ModDownload is { } page ? Localized("UpscalersModWhere") + " " + page : string.Empty
            : string.Format(Localized("UpscalersModStored"), mod.Filename, mod.Count) + (mod.Applied ? " · " + Localized("UpscalersModApplied") : string.Empty);
        addModButton.IsEnabled = idle && sourcePathBox.Text.Trim().Length > 0;
        removeModButton.Visibility = mod is not null ? Visibility.Visible : Visibility.Collapsed;
        removeModButton.IsEnabled = idle;
        var files = detail?.Recipe?.Dependencies?.Where(dependency => dependency.State == "user_file").ToList() ?? new();
        if (dependencyButtons.Children.Count != files.Count * 2 || dependencyButtons.Tag as string != detail?.Game.AppId)
        {
            dependencyButtons.Children.Clear();
            dependencyButtons.Tag = detail?.Game.AppId;
            foreach (var dependency in files)
            {
                var use = new Button { Tag = dependency.Id };
                Prepare(use, "UpscalersUserFileAdd", (_, _) => AddUserFile(dependency.Id));
                use.Content = string.Format(Localized("UpscalersUserFileAdd"), dependency.Name ?? dependency.Id);
                var remove = new Button { Tag = dependency.Id };
                Prepare(remove, "UpscalersUserFileRemove", (_, _) => SourceCall(client.RemoveUserFileAsync(selectedAppId!, dependency.Id, Experimental)));
                remove.Content = string.Format(Localized("UpscalersUserFileRemove"), dependency.Name ?? dependency.Id);
                dependencyButtons.Children.Add(use);
                dependencyButtons.Children.Add(remove);
            }
        }

        foreach (var button in dependencyButtons.Children.OfType<Button>())
        {
            var dependency = files.FirstOrDefault(item => item.Id == button.Tag as string);
            var removing = dependencyButtons.Children.IndexOf(button) % 2 == 1;
            button.Visibility = removing && dependency?.UserState is not ("ready" or "other_version" or "avoid") ? Visibility.Collapsed : Visibility.Visible;
            button.IsEnabled = idle && (removing || sourcePathBox.Text.Trim().Length > 0);
        }

        if (sourcesPanel.Visibility == Visibility.Visible && detail is not null && sourcesAppId != detail.Game.AppId)
        {
            sourcesAppId = detail.Game.AppId;
            LoadCandidates(detail.Game.AppId);
        }
    }

    private async void LoadCandidates(string appId)
    {
        candidateList.Children.Clear();
        var response = await client.ModCandidatesAsync(appId);
        if (appId != selectedAppId || response.Candidates is not { } found)
        {
            return;
        }

        foreach (var candidate in found.Candidates)
        {
            var pick = new Button { Tag = candidate.Path };
            Prepare(pick, "UpscalersSourcePath", (_, _) =>
            {
                sourcePathBox.Text = candidate.Path;
                UpdateActionState();
            });
            pick.Content = candidate.Filename;
            candidateList.Children.Add(pick);
        }
    }

    private void AddMod()
    {
        var password = passwordBox.Visibility == Visibility.Visible && passwordBox.Password.Length > 0 ? passwordBox.Password : null;
        SourceCall(client.AddModAsync(selectedAppId!, sourcePathBox.Text.Trim(), password, Experimental));
    }

    private void AddUserFile(string dependency) =>
        SourceCall(client.AddUserFileAsync(selectedAppId!, dependency, sourcePathBox.Text.Trim(), Experimental));

    private async void SourceCall(System.Threading.Tasks.Task<UpscalersResponse> call)
    {
        if (selectedAppId is not { } appId || gameBusy)
        {
            return;
        }

        gameBusy = true;
        UpdateActionState();
        var response = await call;
        gameBusy = false;
        if (appId != selectedAppId)
        {
            return;
        }

        if (response.Status == UpscalersResponseStatus.Ok && response.Game is { } game)
        {
            detail = game;
            passwordBox.Visibility = Visibility.Collapsed;
            passwordBox.Password = string.Empty;
            ShowResult(Localized("UpscalersApplied"), true);
            RenderView();
            return;
        }

        if (response.ErrorCode is "mod_password" or "mod_password_wrong")
        {
            passwordBox.Visibility = Visibility.Visible;
        }

        ShowResult(ErrorMessage(response.ErrorCode ?? "upscalers_response_unavailable"), false);
        UpdateActionState();
    }
}
