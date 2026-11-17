using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using Windows.ApplicationModel.Activation;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;

namespace PanelDeControl.GameBar;

sealed partial class App : Application
{
    private XboxGameBarWidget? widget;

    public App()
    {
        UnhandledException += (_, args) => CrashLog.Write("unhandled", args.Exception, args.Message);
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            CrashLog.Write("domain", args.ExceptionObject as Exception, args.ExceptionObject?.ToString());
        TaskScheduler.UnobservedTaskException += (_, args) =>
            CrashLog.Write("task", args.Exception);
        try
        {
            InitializeComponent();
        }
        catch (Exception exception)
        {
            CrashLog.Write("app-resources", exception);
            throw;
        }
    }

    protected override void OnActivated(IActivatedEventArgs args)
    {
        StartCompanion();
        try
        {
            ActivateWidget(args);
        }
        catch (Exception exception)
        {
            CrashLog.Write("activate", exception);
            throw;
        }
    }

    private void ActivateWidget(IActivatedEventArgs args)
    {
        if (args.Kind != ActivationKind.Protocol ||
            args is not IProtocolActivatedEventArgs protocol ||
            protocol.Uri.Scheme != "ms-gamebarwidget" ||
            args is not XboxGameBarWidgetActivatedEventArgs widgetArgs ||
            !widgetArgs.IsLaunchActivation ||
            widgetArgs.AppExtensionId != "PanelDeControl")
        {
            return;
        }

        var frame = new Frame();
        Window.Current.Content = frame;
        widget = new XboxGameBarWidget(
            widgetArgs,
            Window.Current.CoreWindow,
            frame);
        frame.Navigate(typeof(ControlPanelWidget), widget);
        widget.GameBarDisplayModeChanged += OnGameBarDisplayModeChanged;
        Window.Current.Closed += OnWidgetClosed;
        Window.Current.Activate();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        StartCompanion();
        var frame = Window.Current.Content as Frame ?? new Frame();
        Window.Current.Content = frame;
        if (frame.Content is null)
        {
            frame.Navigate(typeof(ControlPanelWidget));
        }

        Window.Current.Activate();
    }

    // On some handhelds (ROG Xbox Ally X with Gaming Services 39.118) Windows keeps the Xbox button for Game Bar and
    // Steam never sees it. The companion hears every time Game Bar opens and closes: over Big Picture or the desktop
    // opening is Steam's button for the theme; over a game Game Bar stays usable, and opening and closing it at once
    // (the button pressed twice) is Steam's button. How long it was shown is measured here, where the events arrive,
    // and the reports go out one after another so a slow pipe cannot reorder them.
    private static readonly Stopwatch GameBarShownFor = new();
    private static readonly object GameBarReportGate = new();
    private static Task gameBarReports = Task.CompletedTask;

    private static void OnGameBarDisplayModeChanged(XboxGameBarWidget sender, object args)
    {
        var shown = sender.GameBarDisplayMode == XboxGameBarDisplayMode.Foreground;
        Func<ThemesClient, Task> report;
        lock (GameBarReportGate)
        {
            if (shown == GameBarShownFor.IsRunning)
            {
                return;
            }

            if (shown)
            {
                GameBarShownFor.Restart();
                report = client => client.GameBarShownAsync();
            }
            else
            {
                GameBarShownFor.Stop();
                var milliseconds = GameBarShownFor.ElapsedMilliseconds;
                report = client => client.GameBarHiddenAsync(milliseconds);
            }

            gameBarReports = gameBarReports
                .ContinueWith(_ => report(new ThemesClient()), TaskScheduler.Default)
                .Unwrap()
                .ContinueWith(
                    task => CrashLog.Write("game-bar-report", task.Exception),
                    TaskContinuationOptions.OnlyOnFaulted);
        }
    }

    // Game Bar loads the widget at sign-in even while hidden. The companion keeps Steam themed, so it
    // starts as soon as the package runs, not when the widget is first opened; a second copy exits.
    private static void StartCompanion()
    {
        _ = HardwareBrokerLauncher.EnsureStartedAsync().ContinueWith(
            task => CrashLog.Write("companion-start", task.Exception),
            TaskContinuationOptions.OnlyOnFaulted);
    }

    private void OnWidgetClosed(
        object sender,
        Windows.UI.Core.CoreWindowEventArgs args)
    {
        DisposeCurrentPage();
        if (widget is not null)
        {
            widget.GameBarDisplayModeChanged -= OnGameBarDisplayModeChanged;
        }

        // Closed while Game Bar was open, the widget never hears it close: the next opening must still count.
        lock (GameBarReportGate)
        {
            GameBarShownFor.Reset();
        }

        widget = null;
        Window.Current.Closed -= OnWidgetClosed;
    }

    private static void DisposeCurrentPage()
    {
        if (Window.Current.Content is Frame { Content: IDisposable page })
        {
            page.Dispose();
        }
    }
}
