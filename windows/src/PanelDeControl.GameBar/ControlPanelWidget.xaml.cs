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
    private readonly BrightnessControlClient brightnessClient = new();
    private XboxGameBarWidget? gameBarWidget;
    private CancellationTokenSource? volumeDebounce;
    private CancellationTokenSource? brightnessDebounce;
    private long refreshGeneration;
    private long volumeGeneration;
    private long muteGeneration;
    private long brightnessGeneration;
    private bool snapshotRefreshInProgress;
    private bool volumeRefreshInProgress;
    private bool brightnessRefreshInProgress;
    private bool applyingVolumeReadback;
    private bool applyingMuteReadback;
    private bool applyingBrightnessReadback;
    private bool volumeReady;
    private bool muteReady;
    private bool brightnessReady;
    private bool volumeWritePending;
    private bool muteWritePending;
    private bool brightnessWritePending;
    private bool? lastObservedMuted;
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
        InvalidatePendingOperations();
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
        InvalidatePendingOperations();
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
            InvalidatePendingOperations();
        }
    }

    private async void RefreshButton_Click(object sender, RoutedEventArgs args)
    {
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (disposed)
        {
            return;
        }

        var currentRefreshGeneration = refreshGeneration;
        await Task.WhenAll(
            ApplySnapshotWhenReadyAsync(currentRefreshGeneration),
            ApplyVolumeWhenReadyAsync(currentRefreshGeneration),
            ApplyBrightnessWhenReadyAsync(currentRefreshGeneration));
    }

    private async Task ApplySnapshotWhenReadyAsync(
        long currentRefreshGeneration)
    {
        if (snapshotRefreshInProgress || disposed)
        {
            return;
        }

        snapshotRefreshInProgress = true;
        try
        {
            var snapshot = await telemetryClient.GetSnapshotAsync();
            if (!disposed && currentRefreshGeneration == refreshGeneration)
            {
                ApplySnapshot(snapshot);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                snapshotRefreshInProgress = false;
            }
        }
    }

    private async Task ApplyVolumeWhenReadyAsync(
        long currentRefreshGeneration)
    {
        if (volumeRefreshInProgress || disposed)
        {
            return;
        }

        volumeRefreshInProgress = true;
        var volumeRefreshGeneration = volumeGeneration;
        var muteRefreshGeneration = muteGeneration;
        var volumeWriteWasPendingAtRefreshStart = volumeWritePending;
        var muteWriteWasPendingAtRefreshStart = muteWritePending;
        try
        {
            var volume = await volumeClient.GetAsync();
            if (disposed || currentRefreshGeneration != refreshGeneration)
            {
                return;
            }

            if (!volumeWriteWasPendingAtRefreshStart &&
                !volumeWritePending &&
                volumeRefreshGeneration == volumeGeneration)
            {
                ApplyVolumeResponse(volume);
            }

            if (!muteWriteWasPendingAtRefreshStart &&
                !muteWritePending &&
                muteRefreshGeneration == muteGeneration)
            {
                ApplyMuteResponse(volume);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                volumeRefreshInProgress = false;
            }
        }
    }

    private async Task ApplyBrightnessWhenReadyAsync(
        long currentRefreshGeneration)
    {
        if (brightnessRefreshInProgress || disposed)
        {
            return;
        }

        brightnessRefreshInProgress = true;
        var brightnessRefreshGeneration = brightnessGeneration;
        var brightnessWriteWasPendingAtRefreshStart =
            brightnessWritePending;
        try
        {
            var brightness = await brightnessClient.GetAsync();
            if (!disposed &&
                currentRefreshGeneration == refreshGeneration &&
                !brightnessWriteWasPendingAtRefreshStart &&
                !brightnessWritePending &&
                brightnessRefreshGeneration == brightnessGeneration)
            {
                ApplyBrightnessResponse(brightness, writeAttempted: false);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                brightnessRefreshInProgress = false;
            }
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

    private async void MuteToggle_Toggled(
        object sender,
        RoutedEventArgs args)
    {
        if (disposed ||
            applyingMuteReadback ||
            !muteReady ||
            muteWritePending)
        {
            return;
        }

        var requestedMuted = MuteToggle.IsOn;
        MuteStatus.Text = "Aplicando y verificando…";
        MuteToggle.IsEnabled = false;
        var generation = ++muteGeneration;
        muteWritePending = true;

        try
        {
            var response = await volumeClient.SetMuteAsync(requestedMuted);
            if (!disposed && generation == muteGeneration)
            {
                ApplyMuteResponse(response);
            }
        }
        finally
        {
            if (generation == muteGeneration)
            {
                muteWritePending = false;
                MuteToggle.IsEnabled = muteReady;
            }
        }
    }

    private async void BrightnessSlider_ValueChanged(
        object sender,
        Windows.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs args)
    {
        if (disposed || applyingBrightnessReadback || !brightnessReady)
        {
            return;
        }

        BrightnessStatus.Text = "Aplicando y verificando…";
        brightnessDebounce?.Cancel();
        brightnessDebounce?.Dispose();
        var debounce = new CancellationTokenSource();
        brightnessDebounce = debounce;
        var generation = ++brightnessGeneration;
        brightnessWritePending = true;

        try
        {
            await Task.Delay(
                TimeSpan.FromMilliseconds(150),
                debounce.Token);
            var requestedPercentage = (int)Math.Round(args.NewValue);
            var response = await brightnessClient.SetAsync(requestedPercentage);
            if (!disposed && generation == brightnessGeneration)
            {
                ApplyBrightnessResponse(response, writeAttempted: true);
            }
        }
        catch (OperationCanceledException)
        {
        }
        finally
        {
            if (generation == brightnessGeneration)
            {
                brightnessWritePending = false;
                brightnessDebounce = null;
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

    private void ApplyMuteResponse(VolumeControlResponse response)
    {
        switch (response.Status)
        {
            case ControlStatus.Available:
            case ControlStatus.Applied:
                if (!response.ObservedMuted.HasValue)
                {
                    DisableMuteControl("No se pudo leer el estado de silencio");
                    break;
                }

                ApplyObservedMute(response.ObservedMuted.Value);
                muteReady = true;
                MuteToggle.IsEnabled = !muteWritePending;
                MuteStatus.Text = response.Status == ControlStatus.Applied
                    ? "Cambio aplicado y verificado"
                    : "Estado de silencio disponible";
                break;
            case ControlStatus.Unverifiable:
                RestoreKnownMuteState(response.ObservedMuted);
                MuteStatus.Text = "No se pudo verificar el cambio";
                break;
            case ControlStatus.PermissionRequired:
                DisableMuteControl("Windows requiere permiso para silenciar el audio");
                break;
            case ControlStatus.Unavailable:
                DisableMuteControl("No hay un dispositivo de audio predeterminado");
                break;
            case ControlStatus.Rejected:
                RestoreKnownMuteState(null);
                MuteStatus.Text = "Windows rechazó el cambio";
                break;
            default:
                DisableMuteControl("No se pudo conectar con el control de audio");
                break;
        }
    }

    private void ApplyBrightnessResponse(
        BrightnessControlResponse response,
        bool writeAttempted)
    {
        switch (response.Status)
        {
            case ControlStatus.Available:
            case ControlStatus.Applied:
                ApplyObservedBrightness(response.ObservedPercentage!.Value);
                BrightnessSlider.IsEnabled = true;
                brightnessReady = true;
                BrightnessStatus.Text = response.Status == ControlStatus.Applied
                    ? "Cambio aplicado y verificado"
                    : "Panel integrado disponible";
                break;
            case ControlStatus.Unverifiable:
                if (response.ObservedPercentage.HasValue)
                {
                    ApplyObservedBrightness(response.ObservedPercentage.Value);
                    BrightnessSlider.IsEnabled = true;
                    brightnessReady = true;
                    BrightnessStatus.Text = "El cambio no coincide con el valor leído";
                }
                else
                {
                    DisableBrightnessControl("No se pudo verificar el cambio");
                }

                break;
            case ControlStatus.PermissionRequired:
                DisableBrightnessControl(
                    "Windows denegó el permiso para controlar el brillo");
                break;
            case ControlStatus.Unavailable:
                DisableBrightnessControl(
                    "Brillo del panel integrado no disponible");
                break;
            case ControlStatus.Rejected:
                BrightnessStatus.Text = "Windows rechazó el cambio";
                break;
            default:
                DisableBrightnessControl(
                    writeAttempted
                        ? "No se pudo controlar el brillo del panel integrado"
                        : "No se pudo leer el brillo del panel integrado");
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

    private void ApplyObservedMute(bool muted)
    {
        lastObservedMuted = muted;
        applyingMuteReadback = true;
        try
        {
            MuteToggle.IsOn = muted;
        }
        finally
        {
            applyingMuteReadback = false;
        }
    }

    private void ApplyObservedBrightness(int percentage)
    {
        applyingBrightnessReadback = true;
        try
        {
            BrightnessSlider.Value = percentage;
            BrightnessValue.Text = $"{percentage} %";
        }
        finally
        {
            applyingBrightnessReadback = false;
        }
    }

    private void RestoreKnownMuteState(bool? observedMuted)
    {
        if (observedMuted.HasValue)
        {
            ApplyObservedMute(observedMuted.Value);
        }
        else if (lastObservedMuted.HasValue)
        {
            ApplyObservedMute(lastObservedMuted.Value);
        }

        muteReady = lastObservedMuted.HasValue;
        MuteToggle.IsEnabled = muteReady && !muteWritePending;
    }

    private void DisableVolumeControl(string status)
    {
        volumeReady = false;
        VolumeSlider.IsEnabled = false;
        VolumeStatus.Text = status;
    }

    private void DisableMuteControl(string status)
    {
        if (lastObservedMuted.HasValue)
        {
            ApplyObservedMute(lastObservedMuted.Value);
        }

        muteReady = false;
        MuteToggle.IsEnabled = false;
        MuteStatus.Text = status;
    }

    private void DisableBrightnessControl(string status)
    {
        brightnessReady = false;
        BrightnessSlider.IsEnabled = false;
        BrightnessValue.Text = "—";
        BrightnessStatus.Text = status;
    }

    private void InvalidatePendingOperations()
    {
        refreshGeneration++;
        snapshotRefreshInProgress = false;
        volumeRefreshInProgress = false;
        brightnessRefreshInProgress = false;
        CancelPendingVolumeWrite();
        CancelPendingMuteWrite();
        CancelPendingBrightnessWrite();
    }

    private void CancelPendingVolumeWrite()
    {
        volumeGeneration++;
        volumeWritePending = false;
        volumeDebounce?.Cancel();
        volumeDebounce?.Dispose();
        volumeDebounce = null;
    }

    private void CancelPendingMuteWrite()
    {
        muteGeneration++;
        muteWritePending = false;
        muteReady = false;
        MuteToggle.IsEnabled = false;
        MuteStatus.Text = "Comprobando estado de silencio…";
    }

    private void CancelPendingBrightnessWrite()
    {
        brightnessGeneration++;
        brightnessWritePending = false;
        brightnessReady = false;
        brightnessDebounce?.Cancel();
        brightnessDebounce?.Dispose();
        brightnessDebounce = null;
        BrightnessSlider.IsEnabled = false;
        BrightnessValue.Text = "—";
        BrightnessStatus.Text = "Comprobando panel integrado…";
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
