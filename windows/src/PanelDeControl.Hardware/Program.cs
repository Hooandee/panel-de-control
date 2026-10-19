using PanelDeControl.Hardware.Themes;

namespace PanelDeControl.Hardware;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (!OperatingSystem.IsWindows())
        {
            return 1;
        }

        // The companion starts both at sign-in (themes) and from the widget; one copy owns the pipes.
        using var singleInstance = new Mutex(initiallyOwned: true, @"Local\PanelDeControl.Companion", out var ownsInstance);
        if (!ownsInstance)
        {
            return 0;
        }

        CompanionLog.Write("start", string.Join(' ', args));
        try
        {
            // Process teardown owns cleanup because a timed-out hardware poll may still be active.
            var clock = new SystemClock();
            var localCollector = new SnapshotCollector(
                clock,
                new DeviceIdentityReader(DeviceCatalogResource.TryLoad()),
                new LibreHardwareReader(),
                new PowerStatusReader(),
                new WindowsSensorAccessProbe());
            var serviceClient = new ServiceSnapshotClient();
            var collector = new ServiceBackedSnapshotProvider(
                localCollector,
                serviceClient,
                clock);
            var snapshotServer = new SnapshotPipeServer(
                SnapshotPipeServer.PackagedPipeName,
                collector,
                PackageNamedPipeServerFactory.Create,
                inventoryProvider: new ServiceInventoryProvider(serviceClient, clock));
            var volumeController = new CoreAudioVolumeController(
                new CoreAudioEndpointVolumeProvider());
            var volumeServer = new VolumeControlPipeServer(
                VolumeControlPipeServer.PackagedPipeName,
                volumeController,
                PackageNamedPipeServerFactory.CreateControl);
            var brightnessController = new IntegratedDisplayBrightnessController(
                new WmiDisplayBrightnessProvider());
            var brightnessServer = new BrightnessControlPipeServer(
                BrightnessControlPipeServer.PackagedPipeName,
                brightnessController,
                PackageNamedPipeServerFactory.CreateControl);
            var refreshServer = new RefreshRatePipeServer(
                RefreshRatePipeServer.PackagedPipeName,
                new RefreshRateController(new PrimaryDisplayModeProvider()),
                PackageNamedPipeServerFactory.CreateControl);
            var cpuServer = new CpuControlPipeServer(
                CpuControlPipeServer.PackagedPipeName,
                new CpuController(new ActiveSchemeProcessorPowerSettings()),
                PackageNamedPipeServerFactory.CreateControl);
            var tdpServer = new TdpControlPipeServer(
                TdpControlPipeServer.PackagedPipeName,
                new ServiceTdpClient(),
                new PackagedWidgetClientValidator(),
                PackageNamedPipeServerFactory.CreateControl);

            using var steamDevTools = new SteamDevTools();
            using var themeChannel = new OfficialThemeCatalogSource();
            using var classTable = new ClassTableSource(ThemeLibrary.DefaultRoot);
            var steam = new SteamInstallation();
            var themeService = new ThemeService(ThemeLibrary.DefaultRoot, themeChannel, steam, PackageTempFolder.ResolveOrUnavailable());
            var themeEngine = new SteamThemeEngine(
                steamDevTools,
                steam,
                themeService.EngineInputs,
                SteamThemeHostBundle.Read,
                classTable);
            var themesServer = new ThemesPipeServer(
                ThemesPipeServer.PackagedPipeName,
                new ThemesController(themeService, themeEngine),
                PackageNamedPipeServerFactory.CreateControl);

            using var brokerLifetime = new CancellationTokenSource();
            var token = brokerLifetime.Token;
            await Task.WhenAll(
                SuperviseAsync("snapshot", () => snapshotServer.RunAsync(token), token),
                SuperviseAsync("volume", () => volumeServer.RunUntilCancelledAsync(token), token),
                SuperviseAsync("brightness", () => brightnessServer.RunUntilCancelledAsync(token), token),
                SuperviseAsync("tdp", () => tdpServer.RunUntilCancelledAsync(token), token),
                SuperviseAsync("refresh", () => refreshServer.RunUntilCancelledAsync(token), token),
                SuperviseAsync("cpu", () => cpuServer.RunUntilCancelledAsync(token), token),
                SuperviseAsync("themes.engine", () => themeEngine.RunAsync(token), token),
                SuperviseAsync("themes.pipe", () => themesServer.RunUntilCancelledAsync(token), token))
                .ConfigureAwait(false);
            return 0;
        }
        catch (Exception exception)
        {
            CompanionLog.Write("fatal", exception);
            return 1;
        }
    }

    // One broken pipe or idle snapshot server must not take the whole companion down: it also keeps
    // Steam themed while Game Bar is closed, so every server restarts on its own.
    private static async Task SuperviseAsync(string name, Func<Task> run, CancellationToken cancellationToken)
    {
        var failures = 0;
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await run().ConfigureAwait(false);
                failures = 0;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                CompanionLog.Write($"server.{name}", exception);
                failures = Math.Min(failures + 1, 6);
            }

            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(250 << failures), cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }
    }
}
