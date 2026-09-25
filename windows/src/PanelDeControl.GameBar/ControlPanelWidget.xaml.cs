using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Gaming.XboxGameBar;
using System.Collections.Generic;
using PanelDeControl.Core.Capabilities;
using PanelDeControl.Core.Controls;
using PanelDeControl.Core.Presentation;
using PanelDeControl.Core.Telemetry;
using Windows.Foundation;
using Windows.ApplicationModel.Resources;
using Windows.Storage;
using Windows.System;
using Windows.UI;
using Windows.UI.Core;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Automation;
using Windows.UI.Xaml.Controls;
using Windows.UI.Xaml.Controls.Primitives;
using Windows.UI.Xaml.Media;
using Windows.UI.Xaml.Media.Animation;
using Windows.UI.Composition;
using Windows.UI.Xaml.Hosting;
using System.Numerics;
using Windows.UI.Xaml.Input;
using Windows.UI.Xaml.Navigation;
using Windows.UI.Xaml.Shapes;

namespace PanelDeControl.GameBar;

public sealed partial class ControlPanelWidget : Page, IDisposable
{
    private static readonly ResourceLoader Strings = ResourceLoader.GetForViewIndependentUse();
    private const string AccentSettingKey = "accent";
    private const double ArcCenterX = 100;
    private const double ArcCenterY = 92;
    private const double ArcRadius = 78;

    private readonly DispatcherTimer refreshTimer = new()
    {
        Interval = TimeSpan.FromSeconds(2),
    };
    private readonly TelemetryClient telemetryClient = new();
    private readonly VolumeControlClient volumeClient = new();
    private readonly BrightnessControlClient brightnessClient = new();
    private readonly TdpControlClient tdpClient = new();
    private readonly RefreshRateClient refreshClient = new();
    private readonly CpuControlClient cpuClient = new();
    private CancellationTokenSource? cpuDebounce;
    private bool cpuRefreshInProgress;
    private bool cpuWritePending;
    private bool cpuReady;
    private bool applyingCpuReadback;
    private long cpuGeneration;
    private bool refreshRefreshInProgress;
    private bool refreshWritePending;
    private long refreshControlGeneration;
    private int[] shownRefreshRates = Array.Empty<int>();
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
    private readonly TdpPresentationState tdpPresentation = new();
    private CancellationTokenSource? tdpDebounce;
    private static readonly TimeSpan TdpDebounceDelay = TimeSpan.FromMilliseconds(350);
    private bool? confirmedExperimentalTdpEnabled;
    private bool? lastObservedMuted;
    private bool disposed;

    public ControlPanelWidget()
    {
        InitializeComponent();
        PowerArcTrack.Data = CreatePowerArcGeometry(1);
        PowerArcFill.Data = CreatePowerArcGeometry(0);
        ApplyAccent(ReadSavedAccent());
        BuildAccentSwatches();
        CreateHeroGlow();
        refreshTimer.Tick += OnRefreshTimerTick;
        Loaded += OnLoaded;
        Unloaded += OnUnloaded;
    }

    protected override void OnNavigatedTo(NavigationEventArgs args)
    {
        base.OnNavigatedTo(args);
        if (!layoutBuilt)
        {
            layoutBuilt = true;
            desktopLayout = args.Parameter is not XboxGameBarWidget;
            try
            {
                if (desktopLayout)
                {
                    EnterDesktopLayout();
                }

                BuildSections();
                SelectSection(0);
            }
            catch (Exception exception)
            {
                CrashLog.Write(desktopLayout ? "desktop-layout" : "widget-layout", exception);
            }
        }

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
        heroTimer.Stop();
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
        heroTimer.Stop();
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
            heroTimer.Stop();
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
                Foreground = ResourceBrush("PdcTextMutedBrush"),
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
            ApplyTdpWhenReadyAsync(currentRefreshGeneration),
            ApplyRefreshRateWhenReadyAsync(currentRefreshGeneration),
            ApplyCpuWhenReadyAsync(currentRefreshGeneration));
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

    private async Task ApplyRefreshRateWhenReadyAsync(long currentRefreshGeneration)
    {
        if (refreshRefreshInProgress || refreshWritePending || disposed)
        {
            return;
        }

        refreshRefreshInProgress = true;
        var generation = refreshControlGeneration;
        try
        {
            var response = await refreshClient.GetAsync();
            if (!disposed &&
                currentRefreshGeneration == refreshGeneration &&
                !refreshWritePending &&
                generation == refreshControlGeneration)
            {
                ApplyRefreshRateResponse(response);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                refreshRefreshInProgress = false;
            }
        }
    }

    private async Task ApplyCpuWhenReadyAsync(long currentRefreshGeneration)
    {
        if (cpuRefreshInProgress || cpuWritePending || disposed)
        {
            return;
        }

        cpuRefreshInProgress = true;
        var generation = cpuGeneration;
        try
        {
            var response = await cpuClient.GetAsync();
            if (!disposed &&
                currentRefreshGeneration == refreshGeneration &&
                !cpuWritePending &&
                generation == cpuGeneration)
            {
                ApplyCpuResponse(response);
            }
        }
        finally
        {
            if (currentRefreshGeneration == refreshGeneration)
            {
                cpuRefreshInProgress = false;
            }
        }
    }

    private void ApplyCpuResponse(CpuControlResponse response)
    {
        cpuReady = response.BoostEnabled.HasValue && response.MaximumStatePercent.HasValue;
        applyingCpuReadback = true;
        try
        {
            if (response.BoostEnabled is bool boost)
            {
                CpuBoostToggle.IsOn = boost;
            }

            if (response.MaximumStatePercent is int percent)
            {
                CpuMaximumStateSlider.Value = percent;
                CpuMaximumStateValue.Text = $"{percent} %";
            }
            else
            {
                CpuMaximumStateValue.Text = "—";
            }
        }
        finally
        {
            applyingCpuReadback = false;
        }

        CpuBoostToggle.IsEnabled = cpuReady && !cpuWritePending;
        CpuMaximumStateSlider.IsEnabled = cpuReady && !cpuWritePending;
        CpuControlStatus.Text = response.Status switch
        {
            ControlStatus.Available => string.Empty,
            ControlStatus.Applied => Localized("StatusVerified"),
            ControlStatus.Unverifiable => Localized("StatusNotVerified"),
            ControlStatus.PermissionRequired => Localized("CpuPermissionRequired"),
            ControlStatus.Rejected => Localized("StatusRejected"),
            _ => Localized("CpuUnavailable"),
        };
    }

    private async void CpuBoostToggle_Toggled(object sender, RoutedEventArgs args)
    {
        if (disposed || applyingCpuReadback || !cpuReady || cpuWritePending)
        {
            return;
        }

        var enable = CpuBoostToggle.IsOn;
        await WriteCpuAsync(() => cpuClient.SetBoostAsync(enable));
    }

    private async void CpuMaximumStateSlider_ValueChanged(object sender, RangeBaseValueChangedEventArgs args)
    {
        if (disposed || applyingCpuReadback || !cpuReady)
        {
            return;
        }

        var percent = (int)Math.Round(args.NewValue);
        CpuMaximumStateValue.Text = $"{percent} %";
        cpuDebounce?.Cancel();
        var debounce = cpuDebounce = new CancellationTokenSource();
        try
        {
            await Task.Delay(TimeSpan.FromMilliseconds(250), debounce.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }

        await WriteCpuAsync(() => cpuClient.SetMaximumStateAsync(percent));
    }

    private async Task WriteCpuAsync(Func<Task<CpuControlResponse>> write)
    {
        if (cpuWritePending)
        {
            return;
        }

        cpuWritePending = true;
        var generation = ++cpuGeneration;
        CpuControlStatus.Text = Localized("StatusApplying");
        CpuBoostToggle.IsEnabled = false;
        CpuMaximumStateSlider.IsEnabled = false;
        try
        {
            var response = await write();
            if (!disposed && generation == cpuGeneration)
            {
                cpuWritePending = false;
                ApplyCpuResponse(response);
            }
        }
        finally
        {
            if (generation == cpuGeneration)
            {
                cpuWritePending = false;
            }
        }
    }

    private void ApplyRefreshRateResponse(RefreshRateResponse response)
    {
        var rates = response.Supported.ToArray();
        if (!rates.SequenceEqual(shownRefreshRates))
        {
            shownRefreshRates = rates;
            RefreshRateChips.Children.Clear();
            RefreshRateChips.ColumnDefinitions.Clear();
            foreach (var hertz in rates)
            {
                RefreshRateChips.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                var chip = new Button
                {
                    Content = $"{hertz} Hz",
                    Tag = hertz,
                    Style = (Style)Application.Current.Resources["PdcSegmentButtonStyle"],
                };
                Grid.SetColumn(chip, RefreshRateChips.ColumnDefinitions.Count - 1);
                AutomationProperties.SetName(chip, string.Format(Localized("RefreshRateAutomation"), hertz));
                chip.Click += RefreshRateChip_Click;
                RefreshRateChips.Children.Add(chip);
            }
        }

        foreach (var chip in RefreshRateChips.Children.OfType<Button>())
        {
            var active = Equals(chip.Tag, response.ObservedHertz);
            chip.Background = active
                ? new SolidColorBrush(WithAlpha(ResourceBrush("PdcAccentBrush").Color, 0x70))
                : new SolidColorBrush(Colors.Transparent);
            chip.FontWeight = active ? Windows.UI.Text.FontWeights.SemiBold : Windows.UI.Text.FontWeights.Normal;
            chip.IsEnabled = !refreshWritePending;
        }

        RefreshRateStatus.Text = response.Status switch
        {
            ControlStatus.Available => string.Empty,
            ControlStatus.Applied => Localized("StatusVerified"),
            ControlStatus.Unverifiable => Localized("StatusNotVerified"),
            ControlStatus.Rejected => Localized("StatusRejected"),
            _ => Localized("RefreshRateUnavailable"),
        };
    }

    private async void RefreshRateChip_Click(object sender, RoutedEventArgs args)
    {
        if (disposed || refreshWritePending || sender is not Button { Tag: int hertz })
        {
            return;
        }

        refreshWritePending = true;
        var generation = ++refreshControlGeneration;
        RefreshRateStatus.Text = Localized("StatusApplying");
        foreach (var chip in RefreshRateChips.Children.OfType<Button>())
        {
            chip.IsEnabled = false;
        }

        try
        {
            var response = await refreshClient.SetAsync(hertz);
            if (!disposed && generation == refreshControlGeneration)
            {
                refreshWritePending = false;
                ApplyRefreshRateResponse(response);
            }
        }
        finally
        {
            if (generation == refreshControlGeneration)
            {
                refreshWritePending = false;
            }
        }
    }

    private void ApplySnapshot(HardwareSnapshot snapshot)
    {
        DeviceName.Text = snapshot.DeviceModel;
        BatteryValue.Text = Format(snapshot, "battery.level", "0", "%");
        TileCpuValue.Text = Format(snapshot, "cpu.load", "0", "%");
        TileGpuValue.Text = Format(snapshot, "gpu.load", "0", "%");
        var battery = FindReading(snapshot, "battery.level");
        var batteryColor = BatteryColor(battery);
        var cpuColor = ResourceBrush("PdcAccentBrush").Color;
        var gpuColor = ToColor(AccentPalette.Resolve("mint").Argb);
        SetRing(BatteryRing, battery, batteryColor, RingOuterSize);
        SetRing(CpuRing, FindReading(snapshot, "cpu.load"), cpuColor, RingOuterSize - (2 * RingInset));
        SetRing(GpuRing, FindReading(snapshot, "gpu.load"), gpuColor, RingOuterSize - (4 * RingInset));
        BatteryValue.Foreground = new SolidColorBrush(batteryColor);
        TileCpuValue.Foreground = new SolidColorBrush(cpuColor);
        TileGpuValue.Foreground = new SolidColorBrush(gpuColor);
        ApplyEnergy(snapshot);
        PowerSourceValue.Text = FormatPowerSource(snapshot);
        SystemBatteryValue.Text = Format(snapshot, "battery.level", "0", "%");
        SystemBatteryValue.Foreground = new SolidColorBrush(batteryColor);
        SystemBatteryDetail.Text = PowerDrawDetail.Text;
        ApplyBatteryHealth(snapshot);
        ApplyFan(FanOneValue, snapshot, "fan.cpu.rpm");
        ApplyFan(FanTwoValue, snapshot, "fan.gpu.rpm");
        FanTwoPanel.Visibility = FindReading(snapshot, "fan.gpu.rpm") is null ? Visibility.Collapsed : Visibility.Visible;
        ApplyTemperature(CpuTemperatureValue, snapshot, "cpu.temperature");
        CpuLoadValue.Text = string.Format(Localized("LoadFormat"), Format(snapshot, "cpu.load", "0", "%"));
        ApplyTemperature(GpuTemperatureValue, snapshot, "gpu.temperature");
        GpuLoadValue.Text = string.Format(Localized("LoadFormat"), Format(snapshot, "gpu.load", "0", "%"));
        SetRing(CpuLoadRing, FindReading(snapshot, "cpu.load"), cpuColor, LoadRingSize, LoadRingStroke);
        SetRing(GpuLoadRing, FindReading(snapshot, "gpu.load"), gpuColor, LoadRingSize, LoadRingStroke);

        var available = snapshot.Readings.Any(
            reading => reading.Status == ReadingStatus.Available);
        var unsupported = snapshot.Readings.Any(
            reading => reading.ErrorCode == "device_not_supported");
        var healthy = available && !unsupported;
        ConnectionStatus.Text = unsupported
            ? Localized("DeviceUnrecognized")
            : healthy
                ? string.Empty
                : StatusText(snapshot.Readings.FirstOrDefault());
        ConnectionStatus.Visibility = healthy ? Visibility.Collapsed : Visibility.Visible;
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

    private async void TdpSlider_ValueChanged(object sender, RangeBaseValueChangedEventArgs args)
    {
        if (disposed || applyingTdpReadback || !tdpReady)
        {
            return;
        }

        var watts = (int)Math.Round(args.NewValue);
        tdpPresentation.Select(watts, tdpMinimumWatts, tdpMaximumWatts);
        UpdatePowerArc();
        tdpDebounce?.Cancel();
        var debounce = tdpDebounce = new CancellationTokenSource();
        try
        {
            await Task.Delay(TdpDebounceDelay, debounce.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }

        await ApplyTdpSelectionAsync(watts);
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

        tdpPresentation.Select(requestedWatts, tdpMinimumWatts, tdpMaximumWatts);
        SetTdpSliderValue(tdpPresentation.SelectedWatts);
        UpdatePowerArc();
        PowerStatus.Text = Localized("StatusApplying");
        var generation = ++tdpGeneration;
        tdpWritePending = true;
        UpdateTdpControlAvailability();
        try
        {
            var response = await tdpClient.SetAsync(tdpPresentation.SelectedWatts);
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

        tdpPresentation.Observe(response);

        if (tdpReady)
        {
            tdpMinimumWatts = response.MinimumWatts!.Value;
            tdpMaximumWatts = response.MaximumWatts!.Value;
            applyingTdpReadback = true;
            try
            {
                TdpSlider.Minimum = tdpMinimumWatts;
                TdpSlider.Maximum = tdpMaximumWatts;
                TdpSlider.Value = tdpPresentation.SelectedWatts;
            }
            finally
            {
                applyingTdpReadback = false;
            }

            TdpControls.Visibility = Visibility.Visible;
            PowerReadout.Visibility = Visibility.Visible;
            PowerReadbackHint.Visibility = Visibility.Visible;
            UpdatePowerArc();
            UpdateTdpPresetButtons(response.PresetWatts);
        }
        else
        {
            PowerValue.Text = "—";
            TdpControls.Visibility = Visibility.Collapsed;
            PowerReadout.Visibility = Visibility.Collapsed;
            PowerReadbackHint.Visibility = Visibility.Collapsed;
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
        UpdateHero();
    }

    private void SetTdpSliderValue(int watts)
    {
        applyingTdpReadback = true;
        try
        {
            TdpSlider.Value = watts;
        }
        finally
        {
            applyingTdpReadback = false;
        }
    }

    private void UpdatePowerArc()
    {
        PowerValue.Text = tdpPresentation.AppliedWatts is int watts ? $"{watts} W" : "—";
        PowerLimits.Text = string.Format(
            Localized("PowerLimitsFormat"),
            tdpMinimumWatts,
            tdpMaximumWatts);
        UpdateHero();
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
        TdpSlider.IsEnabled = canWrite;
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
        return CreateArcSegmentGeometry(0, fraction);
    }

    private static PathGeometry CreateArcSegmentGeometry(double from, double to)
    {
        var start = PowerArc.PointAt(from, ArcCenterX, ArcCenterY, ArcRadius);
        var figure = new PathFigure
        {
            StartPoint = new Point(start.X, start.Y),
            IsClosed = false,
        };
        if (to > from)
        {
            var end = PowerArc.PointAt(to, ArcCenterX, ArcCenterY, ArcRadius);
            figure.Segments.Add(new ArcSegment
            {
                Point = new Point(end.X, end.Y),
                Size = new Size(ArcRadius, ArcRadius),
                IsLargeArc = PowerArc.IsLargeArc(to - from),
                SweepDirection = SweepDirection.Clockwise,
            });
        }

        var geometry = new PathGeometry();
        geometry.Figures.Add(figure);
        return geometry;
    }


    private void Page_KeyDown(object sender, KeyRoutedEventArgs args)
    {
        var controlDown = Window.Current.CoreWindow
            .GetKeyState(VirtualKey.Control)
            .HasFlag(CoreVirtualKeyStates.Down);
        var shiftDown = Window.Current.CoreWindow
            .GetKeyState(VirtualKey.Shift)
            .HasFlag(CoreVirtualKeyStates.Down);
        var step = args.Key switch
        {
            VirtualKey.GamepadLeftShoulder => -1,
            VirtualKey.GamepadRightShoulder => 1,
            VirtualKey.Tab when controlDown => shiftDown ? -1 : 1,
            _ => 0,
        };
        if (step == 0)
        {
            return;
        }

        SelectSection((selectedSection + step + sections.Count) % sections.Count);
        args.Handled = true;
    }

    private const double DesktopTwoColumnWidth = 980;
    private const string PinnedSectionId = "settings";
    private readonly List<SectionView> sections = new();
    private int selectedSection;
    private bool layoutBuilt;
    private bool desktopLayout;
    private int desktopColumns;

    private sealed class SectionView
    {
        public SectionView(SectionDefinition definition, Button tab, TextBlock label, Panel panel, IReadOnlyList<FrameworkElement> blocks)
        {
            Definition = definition;
            Tab = tab;
            Label = label;
            Panel = panel;
            Blocks = blocks;
        }

        public SectionDefinition Definition { get; }

        public Button Tab { get; }

        public TextBlock Label { get; }

        public Panel Panel { get; }

        public IReadOnlyList<FrameworkElement> Blocks { get; }
    }

    private void EnterDesktopLayout()
    {
        WidgetShell.Visibility = Visibility.Collapsed;
        DesktopShell.Visibility = Visibility.Visible;
        WidgetShell.Children.Remove(HeaderBlock);
        WidgetShell.Children.Remove(ConnectionStatus);
        WidgetShell.Children.Remove(SectionHeaderBlock);
        WidgetScroller.Content = null;
        DesktopHeaderSlot.Children.Add(HeaderBlock);
        DesktopHeaderSlot.Children.Add(ConnectionStatus);
        DesktopContent.Children.Add(SectionHeaderBlock);
        DesktopContent.Children.Add(SectionHost);
        HeaderDetail.TextWrapping = TextWrapping.Wrap;
        HeaderDetail.TextTrimming = TextTrimming.None;
        SectionHeaderBlock.Margin = new Thickness(0, 0, 0, 24);
        SectionTitle.FontSize = 30;
        SectionDescription.FontSize = 14;
        DesktopScroller.SizeChanged += (_, _) => ReflowDesktopColumns();
    }

    private void ReflowDesktopColumns()
    {
        var columns = DesktopScroller.ActualWidth >= DesktopTwoColumnWidth ? 2 : 1;
        if (!desktopLayout || columns == desktopColumns)
        {
            return;
        }

        desktopColumns = columns;
        foreach (var view in sections)
        {
            var grid = (Grid)view.Panel;
            var stacks = grid.Children.OfType<StackPanel>().ToArray();
            foreach (var stack in stacks)
            {
                stack.Children.Clear();
            }

            var split = columns == 2 && view.Blocks.Count > 1;
            grid.ColumnDefinitions[1].Width = split
                ? new GridLength(1, GridUnitType.Star)
                : new GridLength(0);
            for (var index = 0; index < view.Blocks.Count; index++)
            {
                stacks[split ? index % 2 : 0].Children.Add(view.Blocks[index]);
            }
        }
    }

    private Panel CreateSectionPanel()
    {
        if (!desktopLayout)
        {
            var stack = new StackPanel { Visibility = Visibility.Collapsed };
            stack.ChildrenTransitions = new TransitionCollection
            {
                new EntranceThemeTransition { FromVerticalOffset = 12 },
            };
            return stack;
        }

        var grid = new Grid { Visibility = Visibility.Collapsed, ColumnSpacing = 20 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(0) });
        for (var column = 0; column < 2; column++)
        {
            var stack = new StackPanel();
            stack.ChildrenTransitions = new TransitionCollection
            {
                new EntranceThemeTransition { FromVerticalOffset = 12 },
            };
            Grid.SetColumn(stack, column);
            grid.Children.Add(stack);
        }

        return grid;
    }

    private void BuildSections()
    {
        EnergyTitle.Text = Localized("BlockEnergyTitle");
        SystemBatteryTitle.Text = Localized("BlockBatteryTitle");
        SystemBatteryPending.Text = Localized("ChargeLimitPending");
        BatteryHealthLabel.Text = Localized("BatteryHealthLabel");
        BatteryCapacityLabel.Text = Localized("BatteryCapacityLabel");
        BatteryCyclesLabel.Text = Localized("BatteryCyclesLabel");
        PerformanceTitle.Text = Localized("BlockSteamPerformanceTitle");
        RefreshRateLabel.Text = Localized("RefreshRateLabel");
        CpuControlTitle.Text = Localized("BlockCpuTitle");
        CpuControlNote.Text = Localized("CpuWindowsNote");
        PerformancePending.Text = Localized("PerformancePending");
        FanTitle.Text = Localized("BlockFanRpmTitle");
        FanOneLabel.Text = Localized("FanOne");
        FanTwoLabel.Text = Localized("FanTwo");
        var library = BlockLibrary.Children
            .OfType<FrameworkElement>()
            .Where(element => element.Tag is string)
            .ToDictionary(element => (string)element.Tag);
        foreach (var section in SectionCatalog.All)
        {
            var panel = CreateSectionPanel();
            var blocks = new List<FrameworkElement>();
            foreach (var block in section.Blocks)
            {
                if (library.TryGetValue(section.Id + "." + block.Id, out var element))
                {
                    BlockLibrary.Children.Remove(element);
                    blocks.Add(element);
                }
                else
                {
                    blocks.Add(CreatePendingBlock(section, block));
                }
            }

            var target = desktopLayout ? (Panel)((Grid)panel).Children[0] : panel;
            foreach (var block in blocks)
            {
                target.Children.Add(block);
            }

            SectionHost.Children.Add(panel);
            var label = new TextBlock
            {
                Text = Localized("Nav" + section.ResourceStem),
                FontSize = 13,
                VerticalAlignment = VerticalAlignment.Center,
                Visibility = desktopLayout ? Visibility.Visible : Visibility.Collapsed,
            };
            var content = new StackPanel { Orientation = Orientation.Horizontal, Spacing = desktopLayout ? 12 : 7 };
            content.Children.Add(new FontIcon
            {
                FontFamily = (FontFamily)Application.Current.Resources["PdcIconFontFamily"],
                FontSize = 16,
                Glyph = section.Glyph,
            });
            content.Children.Add(label);
            var tab = new Button
            {
                Style = (Style)Application.Current.Resources["PdcTabButtonStyle"],
                HorizontalAlignment = desktopLayout ? HorizontalAlignment.Stretch : HorizontalAlignment.Left,
                HorizontalContentAlignment = desktopLayout ? HorizontalAlignment.Left : HorizontalAlignment.Center,
                Padding = desktopLayout ? new Thickness(14, 11, 14, 11) : new Thickness(11, 8, 11, 8),
                Content = content,
                Tag = sections.Count,
            };
            AutomationProperties.SetName(tab, Localized("Nav" + section.ResourceStem));
            tab.Click += SectionTab_Click;
            var tabHost = !desktopLayout
                ? SectionTabs
                : section.Id == PinnedSectionId ? DesktopNavPinned : DesktopNav;
            tabHost.Children.Add(tab);
            sections.Add(new SectionView(section, tab, label, panel, blocks));
        }
    }

    private static Border CreatePendingBlock(SectionDefinition section, BlockDefinition block)
    {
        var accent = Lighten(ToColor(section.AccentArgb));
        var layout = new Grid { ColumnSpacing = 14 };
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        layout.Children.Add(new Border
        {
            Width = 38,
            Height = 38,
            CornerRadius = new CornerRadius(12),
            VerticalAlignment = VerticalAlignment.Top,
            Background = new SolidColorBrush(WithAlpha(accent, 0x30)),
            Child = new FontIcon
            {
                FontFamily = (FontFamily)Application.Current.Resources["PdcIconFontFamily"],
                FontSize = 16,
                Glyph = block.Glyph,
                Foreground = new SolidColorBrush(accent),
            },
        });
        var text = new StackPanel();
        text.Children.Add(new TextBlock
        {
            Text = Localized(block.ResourceStem + "Title"),
            Style = (Style)Application.Current.Resources["PdcTitleStyle"],
        });
        text.Children.Add(new TextBlock
        {
            Text = Localized(block.ResourceStem + "Desc"),
            Margin = new Thickness(0, 3, 0, 0),
            Style = (Style)Application.Current.Resources["PdcMutedStyle"],
        });
        text.Children.Add(new TextBlock
        {
            Text = Localized("BlockPending"),
            Margin = new Thickness(0, 8, 0, 0),
            FontSize = 11,
            Foreground = new SolidColorBrush(accent),
            Style = (Style)Application.Current.Resources["PdcCaptionStyle"],
        });
        Grid.SetColumn(text, 1);
        layout.Children.Add(text);
        return new Border
        {
            Style = (Style)Application.Current.Resources["PdcCardStyle"],
            Child = layout,
        };
    }

    private static Color Lighten(Color color)
    {
        byte Mix(byte channel) => (byte)(channel + ((255 - channel) * 0.35));
        return Color.FromArgb(color.A, Mix(color.R), Mix(color.G), Mix(color.B));
    }

    private void SectionTab_Click(object sender, RoutedEventArgs args)
    {
        if (sender is Button { Tag: int index })
        {
            SelectSection(index);
        }
    }

    private void SelectSection(int index)
    {
        selectedSection = index;
        var current = sections[index].Definition;
        var accent = ToColor(current.AccentArgb);
        for (var position = 0; position < sections.Count; position++)
        {
            var view = sections[position];
            var selected = position == index;
            view.Panel.Visibility = selected ? Visibility.Visible : Visibility.Collapsed;
            view.Label.Visibility = selected || desktopLayout ? Visibility.Visible : Visibility.Collapsed;
            view.Tab.Background = new SolidColorBrush(selected ? WithAlpha(accent, 0x70) : Colors.Transparent);
            view.Tab.Foreground = ResourceBrush(selected ? "PdcTextPrimaryBrush" : "PdcTextMutedBrush");
        }

        if (!desktopLayout)
        {
            sections[index].Tab.StartBringIntoView();
        }

        SectionTitle.Text = Localized("Nav" + current.ResourceStem);
        SectionDescription.Text = Localized("Nav" + current.ResourceStem + "Desc");

        var glow = new ColorAnimation
        {
            To = WithAlpha(Lighten(accent), 0x44),
            Duration = new Duration(TimeSpan.FromMilliseconds(420)),
            EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut },
        };
        Storyboard.SetTarget(glow, SectionGlowTop);
        Storyboard.SetTargetProperty(glow, "Color");
        var storyboard = new Storyboard();
        storyboard.Children.Add(glow);
        storyboard.Begin();
    }


    private static Color WithAlpha(Color color, byte alpha)
    {
        return Color.FromArgb(alpha, color.R, color.G, color.B);
    }

    private const double DefaultHeroScaleWatts = 40;
    private static readonly TimeSpan HeroAnimationLength = TimeSpan.FromMilliseconds(450);
    private readonly DispatcherTimer heroTimer = new() { Interval = TimeSpan.FromMilliseconds(16) };
    private double heroScaleWatts = DefaultHeroScaleWatts;
    private double heroShownWatts;
    private double heroFromWatts;
    private double heroTargetWatts;
    private DateTimeOffset heroAnimationStart;
    private PowerZone? heroZone;
    private bool heroScaleFromDevice;
    private HeroMode heroMode;
    private LinearGradientBrush? heroGradient;
    private double? lastDrawWatts;
    private double? lastBatteryLevel;
    private bool lastDrawOnAc;

    private enum HeroMode
    {
        Draw,
        Charge,
        Tdp,
    }

    private void UpdateHero()
    {
        HeroMode mode;
        double? value;
        if (tdpReady)
        {
            mode = HeroMode.Tdp;
            value = tdpPresentation.AppliedWatts ?? tdpPresentation.SelectedWatts;
        }
        else if (lastDrawOnAc && lastBatteryLevel is double level)
        {
            mode = HeroMode.Charge;
            value = level;
        }
        else
        {
            mode = HeroMode.Draw;
            value = lastDrawWatts;
        }

        if (mode != heroMode)
        {
            heroMode = mode;
            heroZone = null;
            heroShownWatts = 0;
        }

        var batteryInVitals = mode == HeroMode.Charge ? Visibility.Collapsed : Visibility.Visible;
        BatteryTrack.Visibility = batteryInVitals;
        BatteryRing.Visibility = batteryInVitals;
        BatteryRow.Visibility = batteryInVitals;
        HeroWattsUnit.Visibility = mode == HeroMode.Charge ? Visibility.Collapsed : Visibility.Visible;
        HeroPercentUnit.Visibility = mode == HeroMode.Charge ? Visibility.Visible : Visibility.Collapsed;
        AnimateHero(value);
        UpdateTdpDecorations();
    }

    private void AnimateHero(double? watts)
    {
        if (watts is not double target)
        {
            heroTimer.Stop();
            heroShownWatts = 0;
            PowerDrawValue.Text = "—";
            heroZone = null;
            PowerZoneLabel.Text = string.Empty;
            SetHeroGlow(null);
            PowerArcFill.Data = CreatePowerArcGeometry(0);
            return;
        }

        heroFromWatts = heroShownWatts;
        heroTargetWatts = target;
        heroAnimationStart = DateTimeOffset.UtcNow;
        if (!heroTimer.IsEnabled)
        {
            heroTimer.Tick -= OnHeroTick;
            heroTimer.Tick += OnHeroTick;
            heroTimer.Start();
        }
    }

    private void OnHeroTick(object sender, object args)
    {
        var progress = Math.Min(1, (DateTimeOffset.UtcNow - heroAnimationStart).TotalMilliseconds / HeroAnimationLength.TotalMilliseconds);
        var eased = 1 - Math.Pow(1 - progress, 3);
        heroShownWatts = heroFromWatts + ((heroTargetWatts - heroFromWatts) * eased);
        RenderHero(heroShownWatts);
        if (progress >= 1)
        {
            heroTimer.Stop();
        }
    }

    private void RenderHero(double watts)
    {
        if (heroMode == HeroMode.Charge)
        {
            RenderChargeHero(watts);
            return;
        }

        if (heroMode == HeroMode.Tdp)
        {
            RenderTdpHero(watts);
            return;
        }

        var fraction = PowerArc.Fraction(watts, 0, heroScaleWatts);
        PowerDrawValue.Text = watts.ToString("0.0");
        PowerArcFill.Data = CreatePowerArcGeometry(fraction);
        PowerArcFill.Stroke = heroGradient ??= HeroGradient();
        if (!heroScaleFromDevice)
        {
            PowerZoneLabel.Text = string.Empty;
            SetHeroGlow(null);
            return;
        }

        var zone = PowerArc.ZoneFor(fraction);
        if (zone == heroZone)
        {
            return;
        }

        heroZone = zone;
        var zoneColor = ToColor(PowerArc.ColorFor(fraction));
        PowerZoneLabel.Text = Localized("PowerZone" + zone);
        PowerZoneLabel.Foreground = new SolidColorBrush(zoneColor);
        SetHeroGlow(zoneColor);
    }

    private void RenderTdpHero(double watts)
    {
        var scaleMaximum = TdpScaleMaximum();
        var fraction = PowerArc.Fraction(watts, tdpMinimumWatts, scaleMaximum);
        var color = ToColor(PowerArc.ColorFor(fraction));
        PowerDrawValue.Text = watts.ToString("0");
        PowerArcFill.Data = CreatePowerArcGeometry(tdpPresentation.AppliedWatts.HasValue ? fraction : 0);
        PowerArcFill.Stroke = new SolidColorBrush(color);
        if (tdpPresentation.AppliedWatts is null)
        {
            PowerZoneLabel.Text = Localized("TdpUnconfirmed");
            PowerZoneLabel.Foreground = ResourceBrush("PdcTextMutedBrush");
            SetHeroGlow(null);
            return;
        }

        PowerZoneLabel.Text = Localized("PowerZone" + PowerArc.ZoneFor(fraction));
        PowerZoneLabel.Foreground = new SolidColorBrush(color);
        SetHeroGlow(color);
    }

    private double TdpScaleMaximum()
    {
        return heroScaleFromDevice ? Math.Max(heroScaleWatts, tdpMaximumWatts) : tdpMaximumWatts;
    }

    private void UpdateTdpDecorations()
    {
        if (heroMode != HeroMode.Tdp || tdpMaximumWatts <= tdpMinimumWatts)
        {
            ChargerBand.Data = null;
            BoostArc.Data = null;
            TdpMarker.Visibility = Visibility.Collapsed;
            return;
        }

        var scaleMaximum = TdpScaleMaximum();
        double FractionOf(double watts) => PowerArc.Fraction(watts, tdpMinimumWatts, scaleMaximum);
        ChargerBand.Data = scaleMaximum > tdpMaximumWatts
            ? CreateArcSegmentGeometry(FractionOf(tdpMaximumWatts), 1)
            : null;
        BoostArc.Data = tdpPresentation.AppliedWatts is int applied && lastDrawWatts is double draw && draw > applied + 0.5
            ? CreateArcSegmentGeometry(FractionOf(applied), FractionOf(Math.Min(draw, scaleMaximum)))
            : null;
        if (tdpPresentation.AppliedWatts == tdpPresentation.SelectedWatts)
        {
            TdpMarker.Visibility = Visibility.Collapsed;
            return;
        }

        var point = PowerArc.PointAt(FractionOf(tdpPresentation.SelectedWatts), ArcCenterX, ArcCenterY, ArcRadius);
        Canvas.SetLeft(TdpMarker, point.X - (TdpMarker.Width / 2));
        Canvas.SetTop(TdpMarker, point.Y - (TdpMarker.Height / 2));
        TdpMarker.Visibility = Visibility.Visible;
    }

    private void RenderChargeHero(double level)
    {
        var fraction = Math.Min(Math.Max(level, 0), 100) / 100;
        var color = BatteryColorFor(level);
        PowerDrawValue.Text = level.ToString("0");
        PowerArcFill.Data = CreatePowerArcGeometry(fraction);
        PowerArcFill.Stroke = new SolidColorBrush(color);
        PowerZoneLabel.Text = Localized("HeroBattery");
        PowerZoneLabel.Foreground = new SolidColorBrush(color);
        SetHeroGlow(color);
    }

    private void SetHeroGlow(Color? color)
    {
        if (heroGlowStop is not null)
        {
            heroGlowStop.Color = color is Color value ? WithAlpha(value, 0x42) : Colors.Transparent;
        }
    }

    private static LinearGradientBrush HeroGradient()
    {
        var gradient = new LinearGradientBrush
        {
            MappingMode = BrushMappingMode.Absolute,
            StartPoint = new Point(ArcCenterX - ArcRadius, 0),
            EndPoint = new Point(ArcCenterX + ArcRadius, 0),
        };
        foreach (var offset in new[] { 0.0, 0.5, 1.0 })
        {
            gradient.GradientStops.Add(new GradientStop { Offset = offset, Color = ToColor(PowerArc.ColorFor(offset)) });
        }

        return gradient;
    }

    private const double RingOuterSize = 132;
    private const double RingInset = 15;
    private const double RingStroke = 11;
    private const double LoadRingSize = 30;
    private const double LoadRingStroke = 4;

    private static void SetRing(Path ring, TelemetryReading? reading, Color color, double size, double stroke = RingStroke)
    {
        var fraction = reading?.Status == ReadingStatus.Available && reading.Value is double value
            ? Math.Min(Math.Max(value, 0), 100) / 100
            : 0;
        ring.Stroke = new SolidColorBrush(color);
        ring.Data = CreateRingGeometry(fraction, size, stroke);
    }

    private static PathGeometry CreateRingGeometry(double fraction, double size, double stroke)
    {
        var radius = (size - stroke) / 2;
        var center = size / 2;
        var geometry = new PathGeometry();
        if (fraction <= 0)
        {
            return geometry;
        }

        var sweep = Math.Min(fraction, 0.9999) * 360;
        Point At(double degrees)
        {
            var radians = (degrees - 90) * Math.PI / 180;
            return new Point(center + (radius * Math.Cos(radians)), center + (radius * Math.Sin(radians)));
        }

        var figure = new PathFigure { StartPoint = At(0), IsClosed = false };
        figure.Segments.Add(new ArcSegment
        {
            Point = At(sweep),
            Size = new Size(radius, radius),
            IsLargeArc = sweep > 180,
            SweepDirection = SweepDirection.Clockwise,
        });
        geometry.Figures.Add(figure);
        return geometry;
    }

    private void ApplyBatteryHealth(HardwareSnapshot snapshot)
    {
        var health = FindReading(snapshot, BatteryHealth.HealthId);
        BatteryHealthValue.Text = Format(snapshot, BatteryHealth.HealthId, "0", "%");
        BatteryHealthValue.Foreground = health?.Status == ReadingStatus.Available && health.Value is double percent
            ? new SolidColorBrush(BatteryColorFor(percent))
            : ResourceBrush("PdcTextMutedBrush");
        var full = FindReading(snapshot, BatteryHealth.FullCapacityId);
        var design = FindReading(snapshot, BatteryHealth.DesignCapacityId);
        BatteryCapacityValue.Text = full?.Value is double charged && design?.Value is double designed &&
            full.Status == ReadingStatus.Available && design.Status == ReadingStatus.Available
                ? string.Format(Localized("BatteryCapacityFormat"), charged / 1000, designed / 1000)
                : StatusText(full);
        var cycles = FindReading(snapshot, BatteryHealth.CyclesId);
        BatteryCyclesValue.Text = cycles?.Status == ReadingStatus.Available && cycles.Value is double count
            ? count.ToString("0")
            : StatusText(cycles);
        foreach (var value in new[] { BatteryHealthValue, BatteryCapacityValue, BatteryCyclesValue })
        {
            value.FontSize = value.Text.Any(char.IsDigit) ? 20 : 13;
        }
    }

    private static void ApplyFan(TextBlock target, HardwareSnapshot snapshot, string id)
    {
        var reading = FindReading(snapshot, id);
        var available = reading?.Status == ReadingStatus.Available && reading.Value.HasValue;
        target.Text = Format(snapshot, id, "0", "RPM");
        target.FontSize = available ? 32 : 15;
        target.Foreground = ResourceBrush(available ? "PdcTextPrimaryBrush" : "PdcTextMutedBrush");
    }

    private static void ApplyTemperature(TextBlock target, HardwareSnapshot snapshot, string id)
    {
        var reading = FindReading(snapshot, id);
        var celsius = reading?.Status == ReadingStatus.Available ? reading.Value : null;
        target.Text = Format(snapshot, id, "0", "°C");
        target.FontSize = celsius.HasValue ? 40 : 15;
        target.Foreground = ResourceBrush(
            celsius >= 85 ? "PdcDangerBrush"
            : celsius >= 70 ? "PdcWarnBrush"
            : celsius.HasValue ? "PdcTextPrimaryBrush"
            : "PdcTextMutedBrush");
    }

    private static Color BatteryColor(TelemetryReading? battery)
    {
        return BatteryColorFor(battery?.Value ?? 100);
    }

    private static Color BatteryColorFor(double level)
    {
        return ResourceBrush(level < 20 ? "PdcDangerBrush" : level < 50 ? "PdcWarnBrush" : "PdcOkBrush").Color;
    }

    private CompositionColorGradientStop? heroGlowStop;

    private void CreateHeroGlow()
    {
        try
        {
            var compositor = ElementCompositionPreview.GetElementVisual(HeroGlowHost).Compositor;
            var brush = compositor.CreateRadialGradientBrush();
            heroGlowStop = compositor.CreateColorGradientStop(0, Colors.Transparent);
            brush.ColorStops.Add(heroGlowStop);
            brush.ColorStops.Add(compositor.CreateColorGradientStop(1, Colors.Transparent));
            var visual = compositor.CreateSpriteVisual();
            visual.Size = new Vector2((float)HeroGlowHost.Width, (float)HeroGlowHost.Height);
            visual.Brush = brush;
            ElementCompositionPreview.SetElementChildVisual(HeroGlowHost, visual);
        }
        catch (Exception exception)
        {
            CrashLog.Write("hero-glow", exception);
        }
    }

    private void BuildAccentSwatches()
    {
        var index = 0;
        foreach (var accent in AccentPalette.All)
        {
            index++;
            var swatch = new Button
            {
                Tag = accent.Id,
                Width = 36,
                Height = 36,
                Padding = new Thickness(0),
                Margin = new Thickness(3),
                CornerRadius = new CornerRadius(18),
                Background = new SolidColorBrush(Colors.Transparent),
                BorderThickness = new Thickness(0),
                IsTabStop = true,
                Content = new Ellipse
                {
                    Width = 26,
                    Height = 26,
                    Fill = new SolidColorBrush(ToColor(accent.Argb)),
                },
            };
            AutomationProperties.SetName(
                swatch,
                string.Format(Localized("AccentSwatchAutomation"), index, AccentPalette.All.Count));
            swatch.Click += AccentSwatch_Click;
            AccentSwatches.Children.Add(swatch);
        }

        MarkSelectedSwatch(ReadSavedAccent().Id);
    }

    private void MarkSelectedSwatch(string id)
    {
        foreach (var swatch in AccentSwatches.Children.OfType<Button>())
        {
            var selected = Equals(swatch.Tag, id);
            swatch.BorderBrush = ResourceBrush("PdcTextPrimaryBrush");
            swatch.BorderThickness = new Thickness(selected ? 2 : 0);
        }
    }

    private void AccentSwatch_Click(object sender, RoutedEventArgs args)
    {
        if (sender is Button { Tag: string id })
        {
            ApplyAccent(AccentPalette.Resolve(id));
            MarkSelectedSwatch(id);
            SelectSection(selectedSection);
            try
            {
                ApplicationData.Current.LocalSettings.Values[AccentSettingKey] = id;
            }
            catch
            {
            }
        }
    }

    private static AccentColor ReadSavedAccent()
    {
        try
        {
            return AccentPalette.Resolve(ApplicationData.Current.LocalSettings.Values[AccentSettingKey] as string);
        }
        catch
        {
            return AccentPalette.Resolve(null);
        }
    }

    private static readonly string[] AccentAliases =
    {
        "ToggleSwitchFillOn",
        "ToggleSwitchFillOnPointerOver",
        "ToggleSwitchFillOnPressed",
    };

    private static void ApplyAccent(AccentColor accent)
    {
        if (Application.Current.Resources["PdcAccentBrush"] is SolidColorBrush brush)
        {
            brush.Color = ToColor(accent.Argb);
            foreach (var key in AccentAliases)
            {
                Application.Current.Resources[key] = brush;
            }
        }
    }

    private static SolidColorBrush ResourceBrush(string key)
    {
        return (SolidColorBrush)Application.Current.Resources[key];
    }

    private static Color ToColor(uint argb)
    {
        return Color.FromArgb((byte)(argb >> 24), (byte)(argb >> 16), (byte)(argb >> 8), (byte)argb);
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
        refreshRefreshInProgress = false;
        refreshWritePending = false;
        refreshControlGeneration++;
        cpuRefreshInProgress = false;
        cpuWritePending = false;
        cpuGeneration++;
        cpuDebounce?.Cancel();
        cpuDebounce = null;
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
        TdpSlider.IsEnabled = false;
        tdpDebounce?.Cancel();
        tdpDebounce?.Dispose();
        tdpDebounce = null;
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

    private void ApplyEnergy(HardwareSnapshot snapshot)
    {
        var draw = FindReading(snapshot, "power.draw");
        heroScaleFromDevice = snapshot.DeviceMaxWatts.HasValue;
        heroScaleWatts = snapshot.DeviceMaxWatts ?? DefaultHeroScaleWatts;
        if (!heroScaleFromDevice)
        {
            heroZone = null;
        }
        var battery = FindReading(snapshot, "battery.level");
        lastDrawWatts = draw?.Status == ReadingStatus.Available ? draw.Value : null;
        lastDrawOnAc = draw?.ErrorCode == "power_draw_on_ac";
        lastBatteryLevel = battery?.Status == ReadingStatus.Available ? battery.Value : null;
        UpdateHero();
        var remaining = FindReading(snapshot, "battery.time_remaining");
        PowerDrawDetail.Text = draw?.ErrorCode switch
        {
            "power_draw_on_ac" => Localized("PowerDrawOnAc"),
            "power_draw_pending" => Localized("PowerDrawPending"),
            _ when remaining?.Status == ReadingStatus.Available && remaining.Value.HasValue =>
                string.Format(
                    Localized("PowerDrawRemainingFormat"),
                    (int)(remaining.Value.Value / 60),
                    (int)(remaining.Value.Value % 60)),
            _ when draw?.Status == ReadingStatus.Available && tdpReady =>
                string.Format(Localized("PowerDrawNowFormat"), draw.Value!.Value),
            _ when draw?.Status == ReadingStatus.Available => Localized("PowerDrawOnBattery"),
            _ => StatusText(draw),
        };

        var mode = FindReading(snapshot, "power.mode");
        var effective = FindReading(snapshot, "power.mode_effective");
        PowerModeValue.Text = ModeName(mode) ?? "—";
        PowerModeDetail.Text = mode?.Value is double selected &&
            effective?.Value is double active &&
            (int)selected != (int)active
                ? string.Format(Localized("PowerModeEffectiveFormat"), ModeName(effective))
                : string.Empty;
    }

    private static string? ModeName(TelemetryReading? reading)
    {
        return reading?.Status == ReadingStatus.Available && reading.Value.HasValue &&
            Enum.IsDefined(typeof(PowerMode), (int)reading.Value.Value)
                ? Localized("PowerMode" + (PowerMode)(int)reading.Value.Value)
                : null;
    }

    private static TelemetryReading? FindReading(HardwareSnapshot snapshot, string id)
    {
        return snapshot.Readings.FirstOrDefault(candidate => candidate.Id == id);
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
