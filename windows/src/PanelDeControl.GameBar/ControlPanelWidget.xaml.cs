using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using PanelDeControl.Core.Controls;
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
    private readonly VolumeControlClient volumeClient = new();
    private XboxGameBarWidget? gameBarWidget;
    private CancellationTokenSource? volumeDebounce;
    private long volumeGeneration;
    private bool refreshInProgress;
    private bool applyingVolumeReadback;
    private bool volumeReady;
    private bool volumeWritePending;
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
        CancelPendingVolumeWrite();
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
        CancelPendingVolumeWrite();
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
            CancelPendingVolumeWrite();
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
            var volumeRefreshGeneration = volumeGeneration;
            var snapshotTask = telemetryClient.GetSnapshotAsync();
            var volumeTask = volumeClient.GetAsync();
            await Task.WhenAll(snapshotTask, volumeTask);
            if (!disposed)
            {
                ApplySnapshot(snapshotTask.Result);
                if (!volumeWritePending &&
                    volumeRefreshGeneration == volumeGeneration)
                {
                    ApplyVolumeResponse(volumeTask.Result);
                }
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
        ConnectionStatus.Text = available
            ? "Telemetría Windows conectada"
            : StatusText(snapshot.Readings.FirstOrDefault());
        ConnectionDot.Fill = available
            ? ConnectedBrush
            : DisconnectedBrush;
    }

    private async void VolumeSlider_ValueChanged(
        object sender,
        Windows.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs args)
    {
        if (disposed || applyingVolumeReadback || !volumeReady)
        {
            return;
        }

        VolumeValue.Text = $"{Math.Round(args.NewValue):0} %";
        VolumeStatus.Text = "Aplicando y verificando…";

        volumeDebounce?.Cancel();
        volumeDebounce?.Dispose();
        var debounce = new CancellationTokenSource();
        volumeDebounce = debounce;
        var generation = ++volumeGeneration;
        volumeWritePending = true;

        try
        {
            await Task.Delay(
                TimeSpan.FromMilliseconds(150),
                debounce.Token);
            var response = await volumeClient.SetAsync(args.NewValue / 100);
            if (!disposed && generation == volumeGeneration)
            {
                ApplyVolumeResponse(response);
            }
        }
        catch (OperationCanceledException)
        {
        }
        finally
        {
            if (generation == volumeGeneration)
            {
                volumeWritePending = false;
                volumeDebounce = null;
                debounce.Dispose();
            }
        }
    }

    private void ApplyVolumeResponse(VolumeControlResponse response)
    {
        switch (response.Status)
        {
            case ControlStatus.Available:
            case ControlStatus.Applied:
                ApplyObservedVolume(response.ObservedLevel!.Value);
                VolumeSlider.IsEnabled = true;
                volumeReady = true;
                VolumeStatus.Text = response.Status == ControlStatus.Applied
                    ? "Cambio aplicado y verificado"
                    : "Audio predeterminado disponible";
                break;
            case ControlStatus.Unverifiable:
                if (response.ObservedLevel.HasValue)
                {
                    ApplyObservedVolume(response.ObservedLevel.Value);
                }

                VolumeSlider.IsEnabled = true;
                volumeReady = true;
                VolumeStatus.Text = "No se pudo verificar el cambio";
                break;
            case ControlStatus.PermissionRequired:
                DisableVolumeControl("Windows requiere permiso para controlar el audio");
                break;
            case ControlStatus.Unavailable:
                DisableVolumeControl("No hay un dispositivo de audio predeterminado");
                break;
            case ControlStatus.Rejected:
                VolumeStatus.Text = "Windows rechazó el cambio";
                break;
            default:
                DisableVolumeControl("No se pudo conectar con el control de audio");
                break;
        }
    }

    private void ApplyObservedVolume(double level)
    {
        applyingVolumeReadback = true;
        try
        {
            var percentage = Math.Round(level * 100);
            VolumeSlider.Value = percentage;
            VolumeValue.Text = $"{percentage:0} %";
        }
        finally
        {
            applyingVolumeReadback = false;
        }
    }

    private void DisableVolumeControl(string status)
    {
        volumeReady = false;
        VolumeSlider.IsEnabled = false;
        VolumeStatus.Text = status;
    }

    private void CancelPendingVolumeWrite()
    {
        volumeGeneration++;
        volumeWritePending = false;
        volumeDebounce?.Cancel();
        volumeDebounce?.Dispose();
        volumeDebounce = null;
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
