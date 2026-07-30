import json
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
BROKER_LAUNCHER = PROJECT_DIR / "HardwareBrokerLauncher.cs"
HARDWARE_DIR = ROOT / "windows" / "src" / "PanelDeControl.Hardware"
PIPE_SERVER = HARDWARE_DIR / "SnapshotPipeServer.cs"
CONTROL_PIPE_SERVER = HARDWARE_DIR / "VolumeControlPipeServer.cs"
PIPE_FACTORY = HARDWARE_DIR / "PackageNamedPipeServerFactory.cs"
BROKER_PROGRAM = HARDWARE_DIR / "Program.cs"
ROOT_LICENSE = ROOT / "LICENSE"
ROOT_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-ci.yml"
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
        self.assertIn("telemetría", app_description)
        self.assertIn("volumen", widget.attrib["Description"].casefold())

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
                "ConnectionCard",
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
        self.assertEqual(
            "Volumen del sistema",
            slider.attrib["AutomationProperties.Name"],
        )

    def test_widget_debounces_volume_writes_and_ignores_stale_responses(self):
        code = WIDGET_CODE.read_text(encoding="utf-8")

        self.assertIn("VolumeSlider_ValueChanged", code)
        self.assertIn("volumeGeneration", code)
        self.assertIn("TimeSpan.FromMilliseconds(150)", code)
        self.assertIn("ControlStatus.Unverifiable", code)
        self.assertIn("ApplyVolumeResponse(volume)", code)

    def test_project_compiles_shared_broker_launcher_and_volume_client(self):
        root = ElementTree.parse(PROJECT).getroot()
        namespace = {"msbuild": "http://schemas.microsoft.com/developer/msbuild/2003"}
        sources = {
            node.attrib["Include"]
            for node in root.findall(".//msbuild:Compile", namespace)
        }

        self.assertIn("HardwareBrokerLauncher.cs", sources)
        self.assertIn("VolumeControlClient.cs", sources)
        self.assertTrue(BROKER_LAUNCHER.is_file())
        self.assertTrue(VOLUME_CLIENT.is_file())

    def test_volume_client_never_retries_an_indeterminate_write(self):
        code = VOLUME_CLIENT.read_text(encoding="utf-8")

        write_started = code.index("requestWriteStarted = true;")
        write_call = code.index("await writer.WriteLineAsync(")
        self.assertLess(write_started, write_call)
        self.assertIn("if (!attempt.RequestWriteStarted)", code)
        self.assertIn("control_response_unavailable", code)
        self.assertIn("VolumeControlResponse.Unverifiable", code)
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
        self.assertIn('"Dispositivo no compatible"', code)
        self.assertIn("var unsupported = snapshot.Readings.Any(", code)
        self.assertIn("available && !unsupported", code)

    def test_broker_uses_package_scoped_pipe_acl(self):
        factory = PIPE_FACTORY.read_text(encoding="utf-8")
        server = PIPE_SERVER.read_text(encoding="utf-8")

        self.assertIn("WellKnownSidType.WorldSid", factory)
        self.assertIn("DeriveAppContainerSidFromAppContainerName", factory)
        self.assertIn("NamedPipeServerStreamAcl.Create", factory)
        self.assertIn('EntryPoint = "GetCurrentPackageFamilyName"', factory)
        self.assertIn(
            'EntryPoint = "DeriveAppContainerSidFromAppContainerName"',
            factory,
        )
        self.assertIn('EntryPoint = "FreeSid"', factory)
        self.assertEqual(3, factory.count("ExactSpelling = true"))
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


if __name__ == "__main__":
    unittest.main()
