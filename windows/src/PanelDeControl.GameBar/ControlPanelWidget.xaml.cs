using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using System.Collections.Generic;
using PanelDeControl.Core.Capabilities;
using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Telemetry;
using Windows.Foundation;
using Windows.ApplicationModel.Resources;
using Windows.UI;
using Windows.UI.Core;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Navigation;

namespace PanelDeControl.GameBar;

public sealed partial class ControlPanelWidget : Page, IDisposable
{
    private static readonly ResourceLoader Strings = ResourceLoader.GetForViewIndependentUse();
    private static readonly SolidColorBrush ConnectedBrush =
        new(Color.FromArgb(255, 103, 212, 255));
    private static readonly SolidColorBrush DisconnectedBrush =
        new(Color.FromArgb(255, 235, 110, 93));
    private static readonly SolidColorBrush PowerSafeBrush =
        new(Color.FromArgb(255, 126, 224, 160));
    private static readonly SolidColorBrush PowerWarningBrush =
        new(Color.FromArgb(255, 255, 180, 84));
    private static readonly SolidColorBrush PowerDangerBrush =
        new(Color.FromArgb(255, 224, 90, 90));

    private readonly DispatcherTimer refreshTimer = new()
    {
        Interval = TimeSpan.FromSeconds(2),
    };
    private readonly TelemetryClient telemetryClient = new();
    private readonly VolumeControlClient volumeClient = new();
    private readonly BrightnessControlClient brightnessClient = new();
    private readonly TdpControlClient tdpClient = new();
    private readonly InventoryClient inventoryClient = new();
    private XboxGameBarWidget? gameBarWidget;
    private CancellationTokenSource? volumeDebounce;
    private CancellationTokenSource? brightnessDebounce;
    private long refreshGeneration;
    private long volumeGeneration;
    private long muteGeneration;
    private long brightnessGeneration;
    private long tdpGeneration;
    private long inventoryGeneration;
    private bool snapshotRefreshInProgress;
    private bool volumeRefreshInProgress;
    private bool brightnessRefreshInProgress;
    private bool tdpRefreshInProgress;
    private bool applyingVolumeReadback;
    private bool applyingMuteReadback;
    private bool applyingBrightnessReadback;
    private bool applyingTdpReadback;
    private bool volumeReady;
    private bool muteReady;
    private bool brightnessReady;
    private bool tdpReady;
    private bool volumeWritePending;
    private bool muteWritePending;
    private bool brightnessWritePending;
    private bool tdpWritePending;
    private bool tdpConflict;
    private int tdpMinimumWatts;
    private int tdpMaximumWatts;
    private int selectedTdpWatts;
    private bool? confirmedExperimentalTdpEnabled;
    private bool? lastObservedMuted;
    private bool disposed;

    public ControlPanelWidget()
    {
        InitializeComponent();
        PowerArcTrack.Data = CreatePowerArcGeometry(1);
        PowerArcFill.Data = CreatePowerArcGeometry(0);
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
        if (DiagnosticsList.Visibility == Visibility.Visible)
        {
            await LoadInventoryAsync();
        }
    }

    private async void DiagnosticsToggle_Click(object sender, RoutedEventArgs args)
    {
        if (DiagnosticsList.Visibility == Visibility.Visible)
        {
            inventoryGeneration++;
            DiagnosticsList.Visibility = Visibility.Collapsed;
            return;
        }

        DiagnosticsList.Visibility = Visibility.Visible;
        await LoadInventoryAsync();
    }

    private async Task LoadInventoryAsync()
    {
        var generation = ++inventoryGeneration;
        ShowDiagnosticsLines(new[] { Localized("DiagnosticsLoading") });
        var inventory = await inventoryClient.GetInventoryAsync();
        if (disposed || generation != inventoryGeneration)
        {
            return;
        }

        ShowDiagnosticsLines(inventory is null
            ? new[] { Localized("DiagnosticsUnavailable") }
            : inventory.Entries.Select(FormatCapability).ToArray());
    }

    private void ShowDiagnosticsLines(IReadOnlyList<string> lines)
    {
        DiagnosticsList.Children.Clear();
        foreach (var line in lines)
        {
            DiagnosticsList.Children.Add(new TextBlock
            {
                Text = line,
                FontSize = 13,
                Margin = new Thickness(0, 4, 0, 0),
                TextWrapping = TextWrapping.Wrap,
                Foreground = new SolidColorBrush(Color.FromArgb(255, 197, 207, 220)),
            });
        }
    }

    private static readonly Dictionary<string, string> CapabilityLabelKeys = new()
    {
        ["sensor.pawnio"] = "CapabilitySensorDriver",
        ["asus.atkacpi"] = "CapabilityAsusAtkacpi",
        ["lenovo.wmi.gamezone"] = "CapabilityLenovoGameZone",
        ["lenovo.wmi.other"] = "CapabilityLenovoOther",
        ["lenovo.wmi.fan"] = "CapabilityLenovoFan",
        ["msi.wmi.acpi"] = "CapabilityMsiAcpi",
        ["rival.asus.armourycrate"] = "CapabilityRivalArmoury",
        ["rival.lenovo.legionspace"] = "CapabilityRivalLegionSpace",
        ["rival.msi.center"] = "CapabilityRivalMsiCenter",
        ["rival.intel.dtt"] = "CapabilityRivalIntelDtt",
        ["service"] = "CapabilityService",
    };

    private static string FormatCapability(CapabilityEntry entry)
    {
        var label = CapabilityLabelKeys.TryGetValue(entry.Id, out var key) ? Localized(key) : entry.Id;
        return string.Format(Localized("CapabilityRowFormat"), label, CapabilityStatusText(entry));
    }

    private static string CapabilityStatusText(CapabilityEntry entry)
    {
        switch (entry.ErrorCode)
        {
            case "service_not_running":
                return Localized("ReadingServiceNotRunning");
            case "service_unavailable":
                return Localized("ReadingServiceUnavailable");
        }

        var isRival = entry.Id.StartsWith("rival.", StringComparison.Ordinal);
        return entry.Status switch
        {
            CapabilityStatus.Present => Localized(isRival ? "RivalRunning" : "CapabilityPresent"),
            CapabilityStatus.Absent => Localized(isRival ? "RivalNotRunning" : "CapabilityAbsent"),
            CapabilityStatus.PermissionRequired => Localized("ReadingPermission"),
            _ => Localized("ReadingFault"),
        };
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
            ApplyBrightnessWhenReadyAsync(currentRefreshGeneration),
            ApplyTdpWhenReadyAsync(currentRefreshGeneration));
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

    private async Task ApplyTdpWhenReadyAsync(
        long currentRefreshGeneration)
    {
        if (tdpRefreshInProgress || disposed)
        {
            return;
        }

        tdpRefreshInProgress = true;
        var controlGeneration = tdpGeneration;
        var writeWasPendingAtRefreshStart = tdpWritePending;
        try
        {
            var response = await tdpClient.GetAsync();
            if (!disposed &&
                currentRefreshGeneration == refreshGeneration &&
                !writeWasPendingAtRefreshStart &&
                !tdpWritePending &&
                controlGeneration == tdpGeneration)
            {
                ApplyTdpResponse(response);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                tdpRefreshInProgress = false;
            }
        }
    }

    private void ApplySnapshot(HardwareSnapshot snapshot)
    {
        DeviceName.Text = snapshot.DeviceModel;
        BatteryValue.Text = Format(snapshot, "battery.level", "0", "%");
        PowerSourceValue.Text = FormatPowerSource(snapshot);
        CpuTemperatureValue.Text = Format(snapshot, "cpu.temperature", "0", "°C");
        CpuLoadValue.Text = string.Format(Localized("LoadFormat"), Format(snapshot, "cpu.load", "0", "%"));
        GpuTemperatureValue.Text = Format(snapshot, "gpu.temperature", "0", "°C");
        GpuLoadValue.Text = string.Format(Localized("LoadFormat"), Format(snapshot, "gpu.load", "0", "%"));
        LastUpdated.Text = snapshot.CapturedAtUtc.ToLocalTime().ToString("HH:mm:ss");

        var available = snapshot.Readings.Any(
            reading => reading.Status == ReadingStatus.Available);
        var unsupported = snapshot.Readings.Any(
            reading => reading.ErrorCode == "device_not_supported");
        ConnectionStatus.Text = unsupported
            ? Localized("DeviceUnrecognized")
            : available
                ? Localized("TelemetryConnected")
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
        VolumeStatus.Text = Localized("StatusApplying");

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
        MuteStatus.Text = Localized("StatusApplying");
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

        BrightnessStatus.Text = Localized("StatusApplying");
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

    private async void ExperimentalTdpToggle_Toggled(
        object sender,
        RoutedEventArgs args)
    {
        if (disposed || applyingTdpReadback || !tdpReady || tdpWritePending)
        {
            return;
        }

        var enable = ExperimentalTdpToggle.IsOn;
        PowerStatus.Text = Localized("StatusApplying");
        var generation = ++tdpGeneration;
        tdpWritePending = true;
        UpdateTdpControlAvailability();
        try
        {
            var response = enable
                ? await tdpClient.EnableExperimentalAsync()
                : await tdpClient.DisableExperimentalAsync();
            if (!disposed && generation == tdpGeneration)
            {
                ApplyTdpResponse(response);
            }
        }
        finally
        {
            if (generation == tdpGeneration)
            {
                tdpWritePending = false;
                UpdateTdpControlAvailability();
            }
        }
    }

    private async void TdpDecreaseButton_Click(
        object sender,
        RoutedEventArgs args)
    {
        await ApplyTdpSelectionAsync(selectedTdpWatts - 1);
    }

    private async void TdpIncreaseButton_Click(
        object sender,
        RoutedEventArgs args)
    {
        await ApplyTdpSelectionAsync(selectedTdpWatts + 1);
    }

    private async void TdpPresetButton_Click(
        object sender,
        RoutedEventArgs args)
    {
        if (sender is Button { Tag: int watts })
        {
            await ApplyTdpSelectionAsync(watts);
        }
    }

    private async Task ApplyTdpSelectionAsync(int requestedWatts)
    {
        if (disposed ||
            !tdpReady ||
            tdpWritePending ||
            tdpConflict ||
            !ExperimentalTdpToggle.IsOn)
        {
            return;
        }

        selectedTdpWatts = Math.Min(
            Math.Max(requestedWatts, tdpMinimumWatts),
            tdpMaximumWatts);
        UpdatePowerArc();
        PowerStatus.Text = Localized("StatusApplying");
        var generation = ++tdpGeneration;
        tdpWritePending = true;
        UpdateTdpControlAvailability();
        try
        {
            var response = await tdpClient.SetAsync(selectedTdpWatts);
            if (!disposed && generation == tdpGeneration)
            {
                ApplyTdpResponse(response);
            }
        }
        finally
        {
            if (generation == tdpGeneration)
            {
                tdpWritePending = false;
                UpdateTdpControlAvailability();
            }
        }
    }

    private void ApplyTdpResponse(TdpControlResponse response)
    {
        tdpReady = response.MinimumWatts.HasValue &&
            response.MaximumWatts.HasValue;
        tdpConflict = response.ErrorCode == "armoury_crate_running";
        applyingTdpReadback = true;
        try
        {
            if (response.ExperimentalStateKnown)
            {
                confirmedExperimentalTdpEnabled =
                    response.ExperimentalEnabled;
                ExperimentalTdpToggle.IsOn = response.ExperimentalEnabled;
            }
            else if (confirmedExperimentalTdpEnabled.HasValue)
            {
                ExperimentalTdpToggle.IsOn =
                    confirmedExperimentalTdpEnabled.Value;
            }
        }
        finally
        {
            applyingTdpReadback = false;
        }

        if (tdpReady)
        {
            tdpMinimumWatts = response.MinimumWatts!.Value;
            tdpMaximumWatts = response.MaximumWatts!.Value;
            selectedTdpWatts = Math.Min(
                Math.Max(
                    response.AppliedWatts ??
                    response.TargetWatts ??
                    response.DefaultWatts ??
                    selectedTdpWatts,
                    tdpMinimumWatts),
                tdpMaximumWatts);
            UpdatePowerArc();
            UpdateTdpPresetButtons(response.PresetWatts);
        }
        else
        {
            PowerValue.Text = "—";
            PowerArcFill.Data = CreatePowerArcGeometry(0);
            HideTdpPresetButtons();
        }

        ManufacturerRecoveryHint.Visibility =
            response.ManufacturerRecoveryUnverified
                ? Visibility.Visible
                : Visibility.Collapsed;
        PowerStatus.Text = response.Status switch
        {
            ControlStatus.Available => response.ExperimentalEnabled
                ? Localized("PowerAvailable")
                : Localized("PowerOptInDisabled"),
            ControlStatus.Applied => Localized("PowerApplied"),
            ControlStatus.Unverifiable => Localized("PowerUnverifiable"),
            ControlStatus.Rejected when tdpConflict =>
                Localized("PowerArmouryConflict"),
            ControlStatus.Rejected when
                response.ErrorCode == "experimental_tdp_disabled" =>
                Localized("PowerOptInDisabled"),
            ControlStatus.Rejected => Localized("PowerRejected"),
            ControlStatus.Unavailable when
                response.ErrorCode == "tdp_profile_unsupported" =>
                Localized("PowerUnsupported"),
            ControlStatus.Unavailable when
                response.ErrorCode == "power_source_unknown" =>
                Localized("PowerSourceUnknown"),
            _ => Localized("PowerServiceUnavailable"),
        };
        UpdateTdpControlAvailability();
    }

    private void UpdatePowerArc()
    {
        var range = tdpMaximumWatts - tdpMinimumWatts;
        var fraction = range <= 0
            ? 0
            : (double)(selectedTdpWatts - tdpMinimumWatts) / range;
        PowerArcFill.Data = CreatePowerArcGeometry(fraction);
        PowerArcFill.Stroke = fraction < 0.55
            ? PowerSafeBrush
            : fraction < 0.82
                ? PowerWarningBrush
                : PowerDangerBrush;
        PowerValue.Text = $"{selectedTdpWatts} W";
        PowerLimits.Text = string.Format(
            Localized("PowerLimitsFormat"),
            tdpMinimumWatts,
            tdpMaximumWatts);
    }

    private void UpdateTdpPresetButtons(IReadOnlyList<int> presets)
    {
        var available = presets
            .Where(watts =>
                watts >= tdpMinimumWatts && watts <= tdpMaximumWatts)
            .Distinct()
            .Take(TdpPresetButtons.Count)
            .ToArray();
        for (var index = 0; index < TdpPresetButtons.Count; index++)
        {
            var button = TdpPresetButtons[index];
            if (index >= available.Length)
            {
                button.Visibility = Visibility.Collapsed;
                button.Tag = null;
                continue;
            }

            var watts = available[index];
            button.Visibility = Visibility.Visible;
            button.Tag = watts;
            button.Content = $"{watts} W";
            AutomationProperties.SetName(
                button,
                string.Format(Localized("PowerPresetAutomation"), watts));
        }
    }

    private void HideTdpPresetButtons()
    {
        foreach (var button in TdpPresetButtons)
        {
            button.Visibility = Visibility.Collapsed;
            button.IsEnabled = false;
            button.Tag = null;
        }
    }

    private void UpdateTdpControlAvailability()
    {
        ExperimentalTdpToggle.IsEnabled = tdpReady && !tdpWritePending;
        var canWrite = tdpReady &&
            ExperimentalTdpToggle.IsOn &&
            !tdpWritePending &&
            !tdpConflict;
        TdpDecreaseButton.IsEnabled = canWrite &&
            selectedTdpWatts > tdpMinimumWatts;
        TdpIncreaseButton.IsEnabled = canWrite &&
            selectedTdpWatts < tdpMaximumWatts;
        foreach (var button in TdpPresetButtons)
        {
            button.IsEnabled = canWrite &&
                button.Visibility == Visibility.Visible;
        }
    }

    private IReadOnlyList<Button> TdpPresetButtons => new[]
    {
        TdpPreset1,
        TdpPreset2,
        TdpPreset3,
        TdpPreset4,
    };

    private static PathGeometry CreatePowerArcGeometry(double fraction)
    {
        const double centerX = 95;
        const double centerY = 88;
        const double radius = 68;
        const double startDegrees = 135;
        const double totalDegrees = 270;
        var clamped = Math.Min(Math.Max(fraction, 0), 1);
        var start = PolarPoint(centerX, centerY, radius, startDegrees);
        var geometry = new PathGeometry();
        var figure = new PathFigure
        {
            StartPoint = start,
            IsClosed = false,
        };
        if (clamped > 0)
        {
            var sweep = totalDegrees * clamped;
            figure.Segments.Add(new ArcSegment
            {
                Point = PolarPoint(
                    centerX,
                    centerY,
                    radius,
                    startDegrees + sweep),
                Size = new Size(radius, radius),
                IsLargeArc = sweep > 180,
                SweepDirection = SweepDirection.Clockwise,
            });
        }

        geometry.Figures.Add(figure);
        return geometry;
    }

    private static Point PolarPoint(
        double centerX,
        double centerY,
        double radius,
        double degrees)
    {
        var radians = degrees * Math.PI / 180;
        return new Point(
            centerX + (radius * Math.Cos(radians)),
            centerY + (radius * Math.Sin(radians)));
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
                    ? Localized("StatusVerified")
                    : Localized("VolumeAvailable");
                break;
            case ControlStatus.Unverifiable:
                if (response.ObservedLevel.HasValue)
                {
                    ApplyObservedVolume(response.ObservedLevel.Value);
                }

                VolumeSlider.IsEnabled = true;
                volumeReady = true;
                VolumeStatus.Text = Localized("StatusNotVerified");
                break;
            case ControlStatus.PermissionRequired:
                DisableVolumeControl(Localized("VolumePermission"));
                break;
            case ControlStatus.Unavailable:
                DisableVolumeControl(Localized("AudioNoDefault"));
                break;
            case ControlStatus.Rejected:
                VolumeStatus.Text = Localized("StatusRejected");
                break;
            default:
                DisableVolumeControl(Localized("AudioConnectFailed"));
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
                    DisableMuteControl(Localized("MuteReadFailed"));
                    break;
                }

                ApplyObservedMute(response.ObservedMuted.Value);
                muteReady = true;
                MuteToggle.IsEnabled = !muteWritePending;
                MuteStatus.Text = response.Status == ControlStatus.Applied
                    ? Localized("StatusVerified")
                    : Localized("MuteAvailable");
                break;
            case ControlStatus.Unverifiable:
                RestoreKnownMuteState(response.ObservedMuted);
                MuteStatus.Text = Localized("StatusNotVerified");
                break;
            case ControlStatus.PermissionRequired:
                DisableMuteControl(Localized("MutePermission"));
                break;
            case ControlStatus.Unavailable:
                DisableMuteControl(Localized("AudioNoDefault"));
                break;
            case ControlStatus.Rejected:
                RestoreKnownMuteState(null);
                MuteStatus.Text = Localized("StatusRejected");
                break;
            default:
                DisableMuteControl(Localized("AudioConnectFailed"));
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
                    ? Localized("StatusVerified")
                    : Localized("BrightnessAvailable");
                break;
            case ControlStatus.Unverifiable:
                if (response.ObservedPercentage.HasValue)
                {
                    ApplyObservedBrightness(response.ObservedPercentage.Value);
                    BrightnessSlider.IsEnabled = true;
                    brightnessReady = true;
                    BrightnessStatus.Text = Localized("BrightnessMismatch");
                }
                else
                {
                    DisableBrightnessControl(Localized("StatusNotVerified"));
                }

                break;
            case ControlStatus.PermissionRequired:
                DisableBrightnessControl(
                    Localized("BrightnessPermission"));
                break;
            case ControlStatus.Unavailable:
                DisableBrightnessControl(
                    Localized("BrightnessUnavailable"));
                break;
            case ControlStatus.Rejected:
                BrightnessStatus.Text = Localized("StatusRejected");
                break;
            default:
                DisableBrightnessControl(
                    writeAttempted
                        ? Localized("BrightnessControlFailed")
                        : Localized("BrightnessReadFailed"));
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
        tdpRefreshInProgress = false;
        CancelPendingVolumeWrite();
        CancelPendingMuteWrite();
        CancelPendingBrightnessWrite();
        CancelPendingTdpWrite();
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
        MuteStatus.Text = Localized("MuteChecking");
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
        BrightnessStatus.Text = Localized("BrightnessChecking");
    }

    private void CancelPendingTdpWrite()
    {
        tdpGeneration++;
        tdpWritePending = false;
        tdpReady = false;
        tdpConflict = false;
        ExperimentalTdpToggle.IsEnabled = false;
        TdpDecreaseButton.IsEnabled = false;
        TdpIncreaseButton.IsEnabled = false;
        foreach (var button in TdpPresetButtons)
        {
            button.IsEnabled = false;
        }

        PowerStatus.Text = Localized("PowerChecking");
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
                ? Localized("PowerAc")
                : Localized("PowerBattery")
            : StatusText(reading);
    }

    private static string StatusText(TelemetryReading? reading)
    {
        if (reading?.ErrorCode == "device_not_supported")
        {
            return Localized("DeviceUnrecognized");
        }

        return reading?.ErrorCode switch
        {
            "sensor_driver_missing" => Localized("ReadingDriverMissing"),
            "sensor_elevation_required" => Localized("ReadingElevation"),
            "service_not_running" => Localized("ReadingServiceNotRunning"),
            "service_unavailable" => Localized("ReadingServiceUnavailable"),
            _ => ReadingStatusText(reading?.Status),
        };
    }

    private static string ReadingStatusText(ReadingStatus? status)
    {
        return status switch
        {
            ReadingStatus.PermissionRequired => Localized("ReadingPermission"),
            ReadingStatus.Fault => Localized("ReadingFault"),
            _ => Localized("ReadingNoData"),
        };
    }

    private static string Localized(string key)
    {
        return Strings.GetString(key);
    }
}
