import json
import re
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = ROOT / "windows" / "src" / "PanelDeControl.GameBar"
PROJECT = PROJECT_DIR / "PanelDeControl.GameBar.csproj"
MANIFEST = PROJECT_DIR / "Package.appxmanifest"
WIDGET = PROJECT_DIR / "ControlPanelWidget.xaml"
WIDGET_CODE = PROJECT_DIR / "ControlPanelWidget.xaml.cs"
APP_CODE = PROJECT_DIR / "App.xaml.cs"
TELEMETRY_CLIENT = PROJECT_DIR / "TelemetryClient.cs"
VOLUME_CLIENT = PROJECT_DIR / "VolumeControlClient.cs"
BRIGHTNESS_CLIENT = PROJECT_DIR / "BrightnessControlClient.cs"
TDP_CLIENT = PROJECT_DIR / "TdpControlClient.cs"
BROKER_LAUNCHER = PROJECT_DIR / "HardwareBrokerLauncher.cs"
HARDWARE_DIR = ROOT / "windows" / "src" / "PanelDeControl.Hardware"
PIPE_SERVER = HARDWARE_DIR / "SnapshotPipeServer.cs"
CONTROL_PIPE_SERVER = HARDWARE_DIR / "VolumeControlPipeServer.cs"
BRIGHTNESS_PIPE_SERVER = HARDWARE_DIR / "BrightnessControlPipeServer.cs"
BRIGHTNESS_PROVIDER = HARDWARE_DIR / "WmiDisplayBrightnessProvider.cs"
BRIGHTNESS_CONTROLLER = HARDWARE_DIR / "IntegratedDisplayBrightnessController.cs"
TDP_PIPE_SERVER = HARDWARE_DIR / "TdpControlPipeServer.cs"
SERVICE_TDP_CLIENT = HARDWARE_DIR / "ServiceTdpClient.cs"
SERVICE_DIR = ROOT / "windows" / "src" / "PanelDeControl.Service"
TDP_CLIENT_VALIDATOR = SERVICE_DIR / "PackagedTdpClientValidator.cs"
PIPE_FACTORY = HARDWARE_DIR / "PackageNamedPipeServerFactory.cs"
BROKER_PROGRAM = HARDWARE_DIR / "Program.cs"
ROOT_LICENSE = ROOT / "LICENSE"
ROOT_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-ci.yml"
STRINGS_DIR = PROJECT_DIR / "Strings"
LANGUAGES = ("en-US", "es", "de", "it", "pt-BR")
XAML_UID = "{http://schemas.microsoft.com/winfx/2006/xaml}Uid"
AUTOMATION = "[using:Windows.UI.Xaml.Automation]AutomationProperties"


def load_strings(language):
    root = ElementTree.parse(STRINGS_DIR / language / "Resources.resw").getroot()
    return {
        node.attrib["name"]: node.findtext("value")
        for node in root.findall("data")
    }


def spanish_automation_name(uid):
    return load_strings("es")[f"{uid}.{AUTOMATION}.Name"]
NUGET_CI_CONFIG = ROOT / "windows" / "NuGet.ci.config"


class GameBarProjectTests(unittest.TestCase):
    def test_project_targets_x64_uwp_and_current_game_bar_sdk(self):
        root = ElementTree.parse(PROJECT).getroot()
        namespace = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}

        self.assertEqual(
            "AppContainerExe",
            root.findtext(".//msbuild:OutputType", namespaces=namespace),
        )
        self.assertEqual(
            "UAP",
            root.findtext(".//msbuild:TargetPlatformIdentifier", namespaces=namespace),
        )
        self.assertEqual(
            {"x64"},
            {
                node.text
                for node in root.findall(".//msbuild:PlatformTarget", namespace)
            },
        )
        package_versions = {
            item.attrib["Include"]: item.findtext(
                "msbuild:Version",
                namespaces=namespace,
            )
            for item in root.findall(".//msbuild:PackageReference", namespace)
        }
        self.assertEqual(
            "7.3.2607010",
            package_versions["Microsoft.Gaming.XboxGameBar"],
        )
        self.assertEqual(
            "6.2.14",
            package_versions["Microsoft.NETCore.UniversalWindowsPlatform"],
        )
        sdk_references = {
            item.attrib["Include"]
            for item in root.findall(".//msbuild:SDKReference", namespace)
        }
        self.assertIn(
            "WindowsDesktop, Version=$(TargetPlatformVersion)",
            sdk_references,
        )
        content_links = {
            item.findtext("msbuild:Link", namespaces=namespace)
            for item in root.findall(".//msbuild:Content", namespace)
        }
        self.assertIn("LICENSE.txt", content_links)
        self.assertIn("THIRD_PARTY_NOTICES.md", content_links)
        self.assertIn(
            r"ThirdPartyLicenses\Microsoft.Gaming.XboxGameBar-LICENSE.txt",
            content_links,
        )
        self.assertNotIn(
            r"ThirdPartyLicenses\Microsoft.NETCore.UWP-LICENSE.txt",
            content_links,
        )
        self.assertNotIn(
            r"ThirdPartyLicenses\Microsoft.NETCore.UWP-NOTICES.txt",
            content_links,
        )
        self.assertIn(
            r"ThirdPartyLicenses\System.IO.Pipes-LICENSE.txt",
            content_links,
        )
        self.assertIn(
            r"ThirdPartyLicenses\System.IO.Pipes.AccessControl-LICENSE.txt",
            content_links,
        )
        self.assertIn(
            r"ThirdPartyLicenses\HidSharp-LICENSE.txt",
            content_links,
        )
        self.assertTrue(ROOT_LICENSE.is_file())
        self.assertTrue(ROOT_NOTICES.is_file())
        gamebar_lock = json.loads(
            (PROJECT_DIR / "packages.lock.json").read_text(encoding="utf-8")
        )
        locked_targets = gamebar_lock["dependencies"]
        expected_framework = "UAP,Version=v10.0.19041"
        expected_runtime_ids = {
            "win10-arm",
            "win10-arm64-aot",
            "win10-arm-aot",
            "win10-x64",
            "win10-x64-aot",
            "win10-x86",
            "win10-x86-aot",
        }
        expected_targets = {expected_framework} | {
            f"{expected_framework}/{runtime_id}"
            for runtime_id in expected_runtime_ids
        }
        self.assertEqual(
            expected_targets,
            set(locked_targets),
        )
        locked_packages = locked_targets[expected_framework]
        self.assertEqual(
            {"type": "Project"},
            locked_packages["paneldecontrol.core"],
        )
        for runtime_id in expected_runtime_ids:
            self.assertNotIn(
                "paneldecontrol.core",
                locked_targets[f"{expected_framework}/{runtime_id}"],
            )
        self.assertEqual(
            {
                "Microsoft.Gaming.XboxGameBar",
                "Microsoft.NETCore.UniversalWindowsPlatform",
                "System.IO.Pipes",
            },
            {
                name
                for name, dependency in locked_packages.items()
                if dependency["type"] == "Direct"
            },
        )
        workflow = WORKFLOW.read_text(encoding="utf-8")
        normalized_workflow = " ".join(workflow.split())
        self.assertIn("/property:RestoreLockedMode=true", workflow)
        self.assertIn("/property:RestoreForceEvaluate=true", workflow)
        self.assertIn(
            "git diff --exit-code -- "
            "windows/src/PanelDeControl.GameBar/packages.lock.json "
            "windows/src/PanelDeControl.Core/packages.lock.json",
            normalized_workflow,
        )
        isolated_packages = (
            "NUGET_PACKAGES: ${{ github.workspace }}\\.nuget\\packages\\"
        )
        self.assertIn(isolated_packages, workflow)
        self.assertIn("--configfile windows/NuGet.ci.config", workflow)
        isolated_config = (
            r"/property:RestoreConfigFile="
            r"${{ github.workspace }}\windows\NuGet.ci.config"
        )
        self.assertIn(
            isolated_config,
            workflow,
        )
        nuget_config = ElementTree.parse(NUGET_CI_CONFIG).getroot()
        self.assertIsNotNone(
            nuget_config.find("./packageSources/clear"),
        )
        self.assertEqual(
            "https://api.nuget.org/v3/index.json",
            nuget_config.find("./packageSources/add").attrib["value"],
        )
        self.assertIsNotNone(
            nuget_config.find("./fallbackPackageFolders/clear"),
        )

    def test_manifest_registers_widget_and_scoped_full_trust_broker(self):
        root = ElementTree.parse(MANIFEST).getroot()
        namespaces = {
            "foundation": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
            "uap3": "http://schemas.microsoft.com/appx/manifest/uap/windows10/3",
            "desktop": "http://schemas.microsoft.com/appx/manifest/desktop/windows10",
            "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
        }

        widget = root.find(
            ".//uap3:AppExtension[@Name='microsoft.gameBarUIExtension']",
            namespaces,
        )
        self.assertIsNotNone(widget)
        self.assertEqual("PanelDeControl", widget.attrib["Id"])
        self.assertEqual(
            "true",
            widget.findtext(
                ".//foundation:PinningSupported",
                namespaces=namespaces,
            ),
        )
        full_trust = root.find(
            ".//desktop:Extension[@Category='windows.fullTrustProcess']",
            namespaces,
        )
        self.assertIsNotNone(full_trust)
        self.assertEqual(
            r"HardwareBroker\PanelDeControl.Hardware.exe",
            full_trust.attrib["Executable"],
        )
        parameter_group = full_trust.find(".//desktop:ParameterGroup", namespaces)
        self.assertEqual("HardwareBroker", parameter_group.attrib["GroupId"])
        self.assertEqual("--gamebar", parameter_group.attrib["Parameters"])
        capabilities = {
            node.attrib["Name"]
            for node in root.findall(".//rescap:Capability", namespaces)
        }
        self.assertEqual({"runFullTrust"}, capabilities)
        app_description = root.find(
            ".//uap:VisualElements",
            {
                "uap": (
                    "http://schemas.microsoft.com/appx/manifest/"
                    "uap/windows10"
                ),
            },
        ).attrib["Description"].casefold()
        self.assertIn("volumen", app_description)
        self.assertIn("brillo", app_description)
        self.assertIn("telemetría", app_description)
        self.assertIn("potencia", app_description)
        self.assertIn("volumen", widget.attrib["Description"].casefold())
        self.assertIn("brillo", widget.attrib["Description"].casefold())
        self.assertIn("potencia", widget.attrib["Description"].casefold())

    def test_broker_payload_metadata_is_bound_to_published_files(self):
        root = ElementTree.parse(PROJECT).getroot()
        namespace = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}
        target = root.find(
            ".//msbuild:Target[@Name='PublishHardwareBroker']",
            namespace,
        )

        payload = target.find(
            ".//msbuild:HardwareBrokerPayload",
            namespace,
        )
        self.assertIsNotNone(payload)
        self.assertEqual(
            "$(HardwareBrokerPublishDir)**\\*",
            payload.attrib["Include"],
        )
        packaged_content = target.find(
            ".//msbuild:Content",
            namespace,
        )
        self.assertIsNotNone(packaged_content)
        self.assertEqual(
            "@(HardwareBrokerPayload)",
            packaged_content.attrib["Include"],
        )
        self.assertEqual(
            "HardwareBroker\\%(HardwareBrokerPayload.RecursiveDir)"
            "%(HardwareBrokerPayload.Filename)"
            "%(HardwareBrokerPayload.Extension)",
            packaged_content.findtext("msbuild:Link", namespaces=namespace),
        )

    def test_manifest_contains_current_game_bar_marshalling_contract(self):
        root = ElementTree.parse(MANIFEST).getroot()
        interfaces = {
            node.attrib["Name"]
            for node in root.iter()
            if node.tag.endswith("Interface")
        }

        self.assertIn(
            "Microsoft.Gaming.XboxGameBar.Private.IXboxGameBarWidgetHost10",
            interfaces,
        )
        self.assertIn(
            "Microsoft.Gaming.XboxGameBar.Private.IXboxGameBarWidgetPrivate6",
            interfaces,
        )
        self.assertIn(
            "Microsoft.Gaming.XboxGameBar.Private.IXboxGameBarWidgetRecordingHost2",
            interfaces,
        )

    def test_widget_has_controller_focus_targets_and_telemetry_cards(self):
        root = ElementTree.parse(WIDGET).getroot()
        names = {
            node.attrib.get("{http://schemas.microsoft.com/winfx/2006/xaml}Name")
            for node in root.iter()
        }

        self.assertTrue(
            {
                "RefreshButton",
                "BatteryCard",
                "CpuCard",
                "GpuCard",
                "ConnectionStatus",
                "TabPower",
                "TabSystem",
                "TabSensors",
                "TabSettings",
            }.issubset(names)
        )
        self.assertEqual(
            "True",
            next(
                node.attrib["IsTabStop"]
                for node in root.iter()
                if node.attrib.get(
                    "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
                )
                == "RefreshButton"
            ),
        )

    def test_widget_has_accessible_system_volume_control(self):
        root = ElementTree.parse(WIDGET).getroot()
        xaml_name = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        slider = next(
            node
            for node in root.iter()
            if node.attrib.get(xaml_name) == "VolumeSlider"
        )
        names = {
            node.attrib.get(xaml_name)
            for node in root.iter()
        }

        self.assertTrue({"VolumeCard", "VolumeValue", "VolumeStatus"}.issubset(names))
        self.assertEqual("0", slider.attrib["Minimum"])
        self.assertEqual("100", slider.attrib["Maximum"])
        self.assertEqual("5", slider.attrib["StepFrequency"])
        self.assertEqual("True", slider.attrib["IsTabStop"])
        self.assertEqual("VolumeSlider", slider.attrib[XAML_UID])
        self.assertEqual("Volumen del sistema", spanish_automation_name("VolumeSlider"))

    def test_widget_debounces_volume_writes_and_ignores_stale_responses(self):
        code = WIDGET_CODE.read_text(encoding="utf-8")
        refresh = code[
            code.index("private async Task RefreshAsync()"):
            code.index("private void ApplySnapshot")
        ]
        normalized_refresh = " ".join(refresh.split())

        self.assertIn("VolumeSlider_ValueChanged", code)
        self.assertIn("volumeGeneration", code)
        self.assertIn("TimeSpan.FromMilliseconds(150)", code)
        self.assertIn("ControlStatus.Unverifiable", code)
        self.assertIn("ApplyVolumeResponse(volume)", code)
        self.assertIn(
            "var volumeWriteWasPendingAtRefreshStart = volumeWritePending;",
            normalized_refresh,
        )
        self.assertIn(
            "if (!volumeWriteWasPendingAtRefreshStart && "
            "!volumeWritePending && "
            "volumeRefreshGeneration == volumeGeneration)",
            normalized_refresh,
        )

    def test_widget_has_accessible_integrated_display_brightness_control(self):
        root = ElementTree.parse(WIDGET).getroot()
        xaml_name = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        slider = next(
            node
            for node in root.iter()
            if node.attrib.get(xaml_name) == "BrightnessSlider"
        )
        names = {
            node.attrib.get(xaml_name)
            for node in root.iter()
        }

        self.assertTrue(
            {"BrightnessCard", "BrightnessValue", "BrightnessStatus"}.issubset(
                names
            )
        )
        self.assertEqual("0", slider.attrib["Minimum"])
        self.assertEqual("100", slider.attrib["Maximum"])
        self.assertEqual("5", slider.attrib["StepFrequency"])
        self.assertEqual("True", slider.attrib["IsTabStop"])
        self.assertEqual("BrightnessSlider", slider.attrib[XAML_UID])
        self.assertEqual("Brillo de la pantalla integrada", spanish_automation_name("BrightnessSlider"))
        self.assertEqual(
            "BrightnessSlider_ValueChanged",
            slider.attrib["ValueChanged"],
        )


    def test_widget_has_accessible_focusable_system_mute_control(self):
        root = ElementTree.parse(WIDGET).getroot()
        xaml_name = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        volume_card = next(
            node
            for node in root.iter()
            if node.attrib.get(xaml_name) == "VolumeCard"
        )
        mute_toggle = next(
            (
                node
                for node in volume_card.iter()
                if node.attrib.get(xaml_name) == "MuteToggle"
            ),
            None,
        )
        names = {
            node.attrib.get(xaml_name)
            for node in volume_card.iter()
        }
        mute_status = next(
            node
            for node in volume_card.iter()
            if node.attrib.get(xaml_name) == "MuteStatus"
        )

        self.assertIsNotNone(mute_toggle)
        self.assertIn("MuteStatus", names)
        self.assertEqual(
            "Polite",
            mute_status.attrib.get("AutomationProperties.LiveSetting"),
        )
        self.assertEqual("False", mute_toggle.attrib["IsEnabled"])
        self.assertEqual("True", mute_toggle.attrib["IsTabStop"])
        self.assertEqual("MuteToggle", mute_toggle.attrib[XAML_UID])
        self.assertEqual(
            "Silenciar audio del sistema",
            spanish_automation_name("MuteToggle"),
        )
        self.assertTrue(load_strings("es")[f"MuteToggle.{AUTOMATION}.HelpText"])
        self.assertEqual("MuteToggle_Toggled", mute_toggle.attrib["Toggled"])

    def test_widget_verifies_mute_independently_and_ignores_stale_responses(self):
        code = WIDGET_CODE.read_text(encoding="utf-8")
        refresh = code[
            code.index("private async Task RefreshAsync()"):
            code.index("private void ApplySnapshot")
        ]
        normalized_refresh = " ".join(refresh.split())

        self.assertIn("MuteToggle_Toggled", code)
        self.assertIn("volumeRefreshGeneration", code)
        self.assertIn("muteRefreshGeneration", code)
        self.assertIn("muteGeneration", code)
        self.assertIn("muteWritePending", code)
        self.assertIn("lastObservedMuted", code)
        self.assertIn("volumeClient.SetMuteAsync", code)
        self.assertIn("ApplyMuteResponse(volume)", code)
        self.assertIn("response.ObservedMuted.HasValue", code)
        self.assertIn("ApplyObservedMute(lastObservedMuted.Value)", code)
        self.assertIn("CancelPendingMuteWrite", code)
        self.assertIn(
            "var muteWriteWasPendingAtRefreshStart = muteWritePending;",
            normalized_refresh,
        )
        self.assertIn(
            "if (!muteWriteWasPendingAtRefreshStart && "
            "!muteWritePending && "
            "muteRefreshGeneration == muteGeneration)",
            normalized_refresh,
        )


    def test_tdp_client_never_retries_an_indeterminate_write(self):
        code = TDP_CLIENT.read_text(encoding="utf-8")

        self.assertIn("SendAsync(TdpControlRequest.Set(requestedWatts))", code)
        self.assertIn("if (!attempt.RequestWriteStarted)", code)
        self.assertIn("TdpControlResponse.Indeterminate", code)
        self.assertIn("experimentalStateKnown: false", code)
        self.assertNotIn("Task.Run", code)

    def test_volume_client_never_retries_an_indeterminate_write(self):
        code = VOLUME_CLIENT.read_text(encoding="utf-8")

        self.assertIn(
            "public Task<VolumeControlResponse> SetMuteAsync(bool requestedMuted)",
            code,
        )
        self.assertIn(
            "SendAsync(VolumeControlRequest.SetMute(requestedMuted))",
            code,
        )
        write_started = code.index("requestWriteStarted = true;")
        write_call = code.index("await writer.WriteLineAsync(")
        self.assertLess(write_started, write_call)
        self.assertIn("if (!attempt.RequestWriteStarted)", code)
        self.assertIn("control_response_unavailable", code)
        self.assertIn("VolumeControlResponse.Unverifiable", code)
        self.assertIn("VolumeControlResponse.MuteUnverifiable", code)
        self.assertNotIn("Task.Run", code)

    def test_brightness_client_never_retries_an_indeterminate_write(self):
        code = BRIGHTNESS_CLIENT.read_text(encoding="utf-8")

        self.assertIn(
            "public Task<BrightnessControlResponse> SetAsync(",
            code,
        )
        self.assertIn(
            "SendAsync(BrightnessControlRequest.Set(requestedPercentage))",
            code,
        )
        write_started = code.index("requestWriteStarted = true;")
        write_call = code.index("await writer.WriteLineAsync(")
        self.assertLess(write_started, write_call)
        self.assertIn("if (!attempt.RequestWriteStarted)", code)
        self.assertIn("brightness_response_unavailable", code)
        self.assertIn("BrightnessControlResponse.Unverifiable", code)
        self.assertNotIn("Task.Run", code)

    def test_required_package_images_are_real_png_files(self):
        expected_sizes = {
            "Square44x44Logo.png": (44, 44),
            "Square150x150Logo.png": (150, 150),
            "StoreLogo.png": (50, 50),
            "SplashScreen.png": (620, 300),
            "WidgetIcon.png": (64, 64),
        }

        for name, expected_size in expected_sizes.items():
            with self.subTest(name=name):
                path = PROJECT_DIR / "Assets" / name
                self.assertTrue(path.is_file())
                with path.open("rb") as image:
                    self.assertEqual(b"\x89PNG\r\n\x1a\n", image.read(8))
                    image.read(8)
                    self.assertEqual(expected_size, struct.unpack(">II", image.read(8)))

    def test_widget_pauses_polling_when_game_bar_hides_it(self):
        code = WIDGET_CODE.read_text(encoding="utf-8")

        self.assertIn("VisibleChanged += OnWidgetVisibilityChanged", code)
        self.assertIn("VisibleChanged -= OnWidgetVisibilityChanged", code)
        self.assertIn("gameBarWidget.Visible", code)
        self.assertIn("Dispatcher.HasThreadAccess", code)
        self.assertIn("Dispatcher.RunAsync", code)

    def test_suspension_does_not_dispose_the_live_widget_page(self):
        code = APP_CODE.read_text(encoding="utf-8")

        self.assertNotIn("Suspending += OnSuspending", code)
        self.assertNotIn("OnSuspending(", code)

    def test_pipe_connection_uses_bounded_async_io_without_worker_thread(self):
        code = TELEMETRY_CLIENT.read_text(encoding="utf-8")

        self.assertIn(
            "ConnectAsync((int)ConnectTimeout.TotalMilliseconds)",
            code,
        )
        self.assertIn("SnapshotTimeout", code)
        self.assertNotIn("Task.Run", code)

    def test_transport_failure_does_not_invent_a_device_identity(self):
        code = TELEMETRY_CLIENT.read_text(encoding="utf-8")

        self.assertIn('"Unknown device"', code)
        self.assertNotIn('"ROG Xbox Ally X"', code)

    def test_widget_surfaces_unsupported_device_state(self):
        code = WIDGET_CODE.read_text(encoding="utf-8")

        self.assertIn('"device_not_supported"', code)
        self.assertIn('Localized("DeviceUnrecognized")', code)
        self.assertIn("var unsupported = snapshot.Readings.Any(", code)
        self.assertIn("available && !unsupported", code)

    def test_broker_uses_package_scoped_pipe_acl(self):
        factory = PIPE_FACTORY.read_text(encoding="utf-8")
        server = PIPE_SERVER.read_text(encoding="utf-8")

        self.assertIn("WellKnownSidType.WorldSid", factory)
        self.assertIn("NamedPipeServerStreamAcl.Create", factory)
        self.assertIn('EntryPoint = "GetCurrentPackageFamilyName"', factory)
        self.assertIn("AppContainerNames.SidFromPackageFamilyName", factory)
        self.assertIn("AppContainerNames.ServerPipeName", factory)
        self.assertNotIn("DeriveAppContainerSidFromAppContainerName", factory)
        self.assertNotIn("new NamedPipeServerStream(", server)
        self.assertIn("catch (IOException)", server)

    def test_broker_hosts_volume_on_a_dedicated_strict_pipe(self):
        factory = PIPE_FACTORY.read_text(encoding="utf-8")
        control_server = CONTROL_PIPE_SERVER.read_text(encoding="utf-8")
        program = BROKER_PROGRAM.read_text(encoding="utf-8")

        self.assertIn(
            "return Create(pipeName, includeWorldAccess: false);",
            factory,
        )
        self.assertIn("if (includeWorldAccess)", factory)
        self.assertIn(r'@"LOCAL\PanelDeControl.Control"', control_server)
        self.assertIn("new VolumeControlPipeServer(", program)
        self.assertIn("PackageNamedPipeServerFactory.CreateControl", program)
        self.assertIn("new CoreAudioEndpointVolumeProvider()", program)

    def test_broker_hosts_brightness_on_a_dedicated_strict_pipe(self):
        factory = PIPE_FACTORY.read_text(encoding="utf-8")
        brightness_server = BRIGHTNESS_PIPE_SERVER.read_text(encoding="utf-8")
        provider = BRIGHTNESS_PROVIDER.read_text(encoding="utf-8")
        controller = BRIGHTNESS_CONTROLLER.read_text(encoding="utf-8")
        program = BROKER_PROGRAM.read_text(encoding="utf-8")

        self.assertIn(
            "return Create(pipeName, includeWorldAccess: false);",
            factory,
        )
        self.assertIn(r'@"LOCAL\PanelDeControl.Display"', brightness_server)
        self.assertIn("new BrightnessControlPipeServer(", program)
        self.assertIn("new WmiDisplayBrightnessProvider()", program)
        self.assertIn("brightnessTask", program)
        self.assertIn(r'@"\\.\root\wmi"', provider)
        self.assertIn("FROM WmiMonitorConnectionParams", provider)
        self.assertIn("FROM WmiMonitorBrightness ", provider)
        self.assertIn("FROM WmiMonitorBrightnessMethods", provider)
        self.assertIn('"WmiSetBrightness"', provider)
        self.assertIn("ReadbackTolerancePercentagePoints = 1", controller)
        self.assertNotIn("DeviceIdentity", provider)
        self.assertNotIn("DeviceIdentity", controller)

    def test_broker_relays_tdp_without_owning_hardware(self):
        server = TDP_PIPE_SERVER.read_text(encoding="utf-8")
        client = SERVICE_TDP_CLIENT.read_text(encoding="utf-8")
        program = BROKER_PROGRAM.read_text(encoding="utf-8")

        self.assertIn(r'@"LOCAL\PanelDeControl.Tdp"', server)
        self.assertIn('PipeName = "PanelDeControl.Service.Tdp"', client)
        self.assertIn("ServicePipeConnector.Connect", client)
        self.assertIn("new TdpControlPipeServer(", program)
        self.assertIn("new ServiceTdpClient()", program)
        self.assertNotIn("ATKACPI", server)
        self.assertNotIn("ATKACPI", client)

    def test_tdp_service_pins_the_package_family_and_broker_location(self):
        manifest = ElementTree.parse(MANIFEST).getroot()
        identity = manifest.find(
            "{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Identity"
        )
        validator = TDP_CLIENT_VALIDATOR.read_text(encoding="utf-8")

        self.assertEqual("PanelDeControl.Windows", identity.attrib["Name"])
        self.assertEqual("CN=Hooandee", identity.attrib["Publisher"])
        self.assertIn('PackageName = "PanelDeControl.Windows"', validator)
        self.assertIn('PackagePublisher = "CN=Hooandee"', validator)
        self.assertIn("PackageFamilyNameFromFullName", validator)
        self.assertIn("PackageFamilyNameFromId", validator)
        self.assertIn("GetPackagePathByFullName", validator)
        self.assertIn(r'@"HardwareBroker\PanelDeControl.Hardware.exe"', validator)

    def test_brightness_timeouts_cover_full_verified_set(self):
        provider = BRIGHTNESS_PROVIDER.read_text(encoding="utf-8")
        server = BRIGHTNESS_PIPE_SERVER.read_text(encoding="utf-8")
        client = BRIGHTNESS_CLIENT.read_text(encoding="utf-8")

        provider_timeout = re.search(
            r"OperationTimeout\s*=\s*TimeSpan\.FromMilliseconds\((\d+)\)",
            provider,
        )
        server_timeout = re.search(
            r"DefaultOperationTimeout\s*=\s*TimeSpan\.FromSeconds\((\d+)\)",
            server,
        )
        client_timeout = re.search(
            r"ResponseTimeout\s*=\s*TimeSpan\.FromSeconds\((\d+)\)",
            client,
        )

        self.assertIsNotNone(provider_timeout)
        self.assertIsNotNone(server_timeout)
        self.assertIsNotNone(client_timeout)
        provider_budget_ms = int(provider_timeout.group(1))
        server_budget_ms = int(server_timeout.group(1)) * 1000
        client_budget_ms = int(client_timeout.group(1)) * 1000
        self.assertGreater(server_budget_ms, provider_budget_ms * 3)
        self.assertGreater(client_budget_ms, server_budget_ms)


if __name__ == "__main__":
    unittest.main()


class ProxyStubTests(unittest.TestCase):
    def test_every_marshalled_interface_has_a_unique_id(self):
        interfaces = re.findall(
            r'<Interface Name="([^"]+)" InterfaceId="([^"]+)"',
            MANIFEST.read_text(encoding="utf-8"),
        )
        ids = [interface_id.upper() for _, interface_id in interfaces]

        self.assertTrue(interfaces)
        self.assertEqual(len(ids), len(set(ids)), [name for name, _ in interfaces])

    def test_notification_host_uses_the_id_game_bar_registers(self):
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn(
            'IXboxGameBarWidgetNotificationHost" InterfaceId="6F68D392-E4A9-46F7-A024-5275BC2FE7BA"',
            manifest,
        )


class SideloadPackageTests(unittest.TestCase):
    def test_ci_builds_a_native_sideload_package(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        project = PROJECT.read_text(encoding="utf-8")

        self.assertIn("/property:UapAppxPackageBuildMode=SideloadOnly", workflow)
        self.assertNotIn("UapAppxPackageBuildMode=CI", workflow)
        self.assertIn("<UseDotNetNativeToolchain>true</UseDotNetNativeToolchain>", project)


class GameBarLocalizationTests(unittest.TestCase):
    def test_every_language_ships_the_same_non_empty_keys(self):
        reference = load_strings("en-US")
        self.assertTrue(reference)
        for language in LANGUAGES:
            strings = load_strings(language)
            self.assertEqual(set(reference), set(strings), language)
            for key, value in strings.items():
                self.assertTrue(value and value.strip(), f"{language}:{key}")

    def test_every_language_is_packaged_and_english_is_the_fallback(self):
        project = PROJECT.read_text(encoding="utf-8")
        self.assertIn("<DefaultLanguage>en-US</DefaultLanguage>", project)
        for language in LANGUAGES:
            self.assertIn(
                f'<PRIResource Include="Strings\\{language}\\Resources.resw" />',
                project,
            )

    def test_every_xaml_uid_is_localized(self):
        strings = load_strings("en-US")
        uids = {
            node.attrib[XAML_UID]
            for node in ElementTree.parse(WIDGET).getroot().iter()
            if XAML_UID in node.attrib
        }
        self.assertTrue(uids)
        for uid in uids:
            self.assertTrue(
                any(key.startswith(f"{uid}.") for key in strings),
                uid,
            )

    def test_widget_has_no_hard_coded_visible_text(self):
        allowed = {"—", "↻", "CPU", "GPU", "W"}
        visible = (
            "Text",
            "Content",
            "OnContent",
            "OffContent",
            "AutomationProperties.Name",
            "AutomationProperties.HelpText",
        )
        for node in ElementTree.parse(WIDGET).getroot().iter():
            for attribute in visible:
                value = node.attrib.get(attribute)
                if value is not None and not value.startswith("{"):
                    self.assertIn(value, allowed, f"{node.tag} {attribute}")

    def test_code_behind_only_uses_known_resource_keys(self):
        strings = load_strings("en-US")
        code = WIDGET_CODE.read_text(encoding="utf-8")
        keys = set(re.findall(r'Localized\("([A-Za-z]+)"\)', code))
        self.assertTrue(keys)
        self.assertTrue(keys.issubset(strings), keys - set(strings))
        self.assertNotRegex(code, r'\.Text = "[^"—]')


class DiagnosticsCardTests(unittest.TestCase):
    def test_every_capability_id_has_a_localized_label(self):
        ids_source = (HARDWARE_DIR / "Capabilities" / "CapabilityIds.cs").read_text(encoding="utf-8")
        ids = set(re.findall(r'const string \w+ = "([^"]+)";', ids_source))
        code = WIDGET_CODE.read_text(encoding="utf-8")
        mapping = dict(re.findall(r'\["([^"]+)"\] = "([A-Za-z]+)"', code))
        strings = load_strings("en-US")

        self.assertTrue(ids)
        self.assertEqual(ids, set(mapping))
        self.assertTrue(set(mapping.values()).issubset(strings), set(mapping.values()) - set(strings))


class DesignSystemTests(unittest.TestCase):
    def test_widget_and_app_never_hard_code_colours(self):
        for path in (WIDGET, PROJECT_DIR / "App.xaml"):
            xaml = path.read_text(encoding="utf-8")
            self.assertNotRegex(xaml, r'"#[0-9A-Fa-f]{6,8}"', path.name)
        code = WIDGET_CODE.read_text(encoding="utf-8")
        self.assertNotIn("Color.FromArgb(255,", code)

    def test_app_merges_the_generated_tokens(self):
        app = (PROJECT_DIR / "App.xaml").read_text(encoding="utf-8")
        project = PROJECT.read_text(encoding="utf-8")
        self.assertIn('Source="ms-appx:///Theme/PdcTokens.xaml"', app)
        self.assertIn('<Page Include="Theme\\PdcTokens.xaml">', project)
        self.assertIn('x:Key="PdcAccentBrush"', (PROJECT_DIR / "Theme" / "PdcTokens.xaml").read_text(encoding="utf-8"))

    def test_every_power_zone_has_a_localized_label(self):
        strings = load_strings("en-US")
        for zone in ("Save", "Eco", "Balanced", "Hot", "Turbo"):
            self.assertIn(f"PowerZone{zone}", strings)
        power_arc = (ROOT / "windows" / "src" / "PanelDeControl.Core" / "Presentation" / "PowerArc.cs").read_text(encoding="utf-8")
        self.assertEqual(
            ["Save", "Eco", "Balanced", "Hot", "Turbo"],
            re.findall(r"^\s{4}(\w+),$", power_arc.split("public enum PowerZone", 1)[1].split("}", 1)[0], re.M),
        )


class EnergyCardTests(unittest.TestCase):
    def test_every_power_mode_has_a_localized_name(self):
        strings = load_strings("en-US")
        modes = (ROOT / "windows" / "src" / "PanelDeControl.Core" / "Telemetry" / "PowerModes.cs").read_text(encoding="utf-8")
        names = re.findall(r"^\s{4}(\w+) = \d+,$", modes, re.M)
        self.assertEqual(["BestEfficiency", "Balanced", "BetterPerformance", "BestPerformance"], names)
        for name in names:
            self.assertIn(f"PowerMode{name}", strings)
