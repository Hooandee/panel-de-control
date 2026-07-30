using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using PanelDeControl.Core.Telemetry;
using Windows.UI;
using Windows.UI.Core;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Navigation;

namespace PanelDeControl.GameBar;

public sealed partial class ControlPanelWidget : Page, IDisposable
{
    private static readonly SolidColorBrush ConnectedBrush =
        new(Color.FromArgb(255, 103, 212, 255));
    private static readonly SolidColorBrush DisconnectedBrush =
        new(Color.FromArgb(255, 235, 110, 93));

    private readonly DispatcherTimer refreshTimer = new()
    {
        Interval = TimeSpan.FromSeconds(2),
    };
    private readonly TelemetryClient telemetryClient = new();
    private XboxGameBarWidget? gameBarWidget;
    private bool refreshInProgress;
    private bool disposed;

    public ControlPanelWidget()
    {
        InitializeComponent();
        refreshTimer.Tick += OnRefreshTimerTick;
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    protected override void OnNavigatedTo(NavigationEventArgs args)
    {
        base.OnNavigatedTo(args);
        if (args.Parameter is XboxGameBarWidget widget)
        {
            gameBarWidget = widget;
            gameBarWidget.VisibleChanged += OnWidgetVisibilityChanged;
            RefreshButton.Focus(FocusState.Programmatic);
        }
    }

    public void Dispose()
    {
        if (disposed)
        {
            return;
        }

        disposed = true;
        refreshTimer.Stop();
        refreshTimer.Tick -= OnRefreshTimerTick;
        if (gameBarWidget is not null)
        {
            gameBarWidget.VisibleChanged -= OnWidgetVisibilityChanged;
            gameBarWidget = null;
        }

        Loaded -= OnLoaded;
        Unloaded -= OnUnloaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs args)
    {
        if (gameBarWidget is null || gameBarWidget.Visible)
        {
            refreshTimer.Start();
            await RefreshAsync();
        }
    }

    private void OnUnloaded(object sender, RoutedEventArgs args)
    {
        refreshTimer.Stop();
    }

    private async void OnRefreshTimerTick(object sender, object args)
    {
        await RefreshAsync();
    }

    private async void OnWidgetVisibilityChanged(XboxGameBarWidget sender, object args)
    {
        if (!Dispatcher.HasThreadAccess)
        {
            await Dispatcher.RunAsync(
                CoreDispatcherPriority.Normal,
                () => OnWidgetVisibilityChanged(sender, args));
            return;
        }

        if (disposed)
        {
            return;
        }

        if (sender.Visible)
        {
            refreshTimer.Start();
            await RefreshAsync();
        }
        else
        {
            refreshTimer.Stop();
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs args)
    {
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (refreshInProgress || disposed)
        {
            return;
        }

        refreshInProgress = true;
        try
        {
            var snapshot = await telemetryClient.GetSnapshotAsync();
            if (!disposed)
            {
                ApplySnapshot(snapshot);
            }
        }
        finally
        {
            refreshInProgress = false;
        }
    }

    private void ApplySnapshot(HardwareSnapshot snapshot)
    {
        DeviceName.Text = snapshot.DeviceModel;
        BatteryValue.Text = Format(snapshot, "battery.level", "0", "%");
        PowerSourceValue.Text = FormatPowerSource(snapshot);
        CpuTemperatureValue.Text = Format(snapshot, "cpu.temperature", "0", "°C");
        CpuLoadValue.Text = $"Carga {Format(snapshot, "cpu.load", "0", "%")}";
        GpuTemperatureValue.Text = Format(snapshot, "gpu.temperature", "0", "°C");
        GpuLoadValue.Text = $"Carga {Format(snapshot, "gpu.load", "0", "%")}";
        LastUpdated.Text = snapshot.CapturedAtUtc.ToLocalTime().ToString("HH:mm:ss");

        var available = snapshot.Readings.Any(
            reading => reading.Status == ReadingStatus.Available);
        var unsupported = snapshot.Readings.Any(
            reading => reading.ErrorCode == "device_not_supported");
        ConnectionStatus.Text = unsupported
            ? "Dispositivo no compatible"
            : available
                ? "Telemetría Windows conectada"
                : StatusText(snapshot.Readings.FirstOrDefault());
        ConnectionDot.Fill = available && !unsupported
            ? ConnectedBrush
            : DisconnectedBrush;
    }

    private static string Format(
        HardwareSnapshot snapshot,
        string id,
        string format,
        string unit)
    {
        var reading = snapshot.Readings.FirstOrDefault(candidate => candidate.Id == id);
        return reading?.Status == ReadingStatus.Available && reading.Value.HasValue
            ? $"{reading.Value.Value.ToString(format)} {unit}"
            : StatusText(reading);
    }

    private static string FormatPowerSource(HardwareSnapshot snapshot)
    {
        var reading = snapshot.Readings.FirstOrDefault(
            candidate => candidate.Id == "power.ac");
        return reading?.Status == ReadingStatus.Available && reading.Value.HasValue
            ? reading.Value.Value >= 1
                ? "Conectada a corriente"
                : "Usando batería"
            : StatusText(reading);
    }

    private static string StatusText(TelemetryReading? reading)
    {
        if (reading?.ErrorCode == "device_not_supported")
        {
            return "Dispositivo no compatible";
        }

        return reading?.Status switch
        {
            ReadingStatus.PermissionRequired => "Necesita permiso",
            ReadingStatus.Fault => "Error de lectura",
            _ => "Sin datos",
        };
    }
}
