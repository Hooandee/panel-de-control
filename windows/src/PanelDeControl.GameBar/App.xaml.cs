using System;
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
        System.Threading.Tasks.TaskScheduler.UnobservedTaskException += (_, args) =>
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
        Window.Current.Closed += OnWidgetClosed;
        Window.Current.Activate();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var frame = Window.Current.Content as Frame ?? new Frame();
        Window.Current.Content = frame;
        if (frame.Content is null)
        {
            frame.Navigate(typeof(ControlPanelWidget));
        }

        Window.Current.Activate();
    }

    private void OnWidgetClosed(
        object sender,
        Windows.UI.Core.CoreWindowEventArgs args)
    {
        DisposeCurrentPage();
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
