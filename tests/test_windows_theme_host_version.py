import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_companion_expects_the_bundled_theme_host_version():
    host = (ROOT / "src/windowsThemeHost/host.ts").read_text(encoding="utf-8")
    engine = (ROOT / "windows/src/PanelDeControl.Hardware/Themes/SteamThemeEngine.cs").read_text(encoding="utf-8")
    bundled = re.search(r"WINDOWS_THEME_HOST_VERSION = (\d+);", host)
    expected = re.search(r"public const int HostVersion = (\d+);", engine)
    assert bundled and expected
    assert bundled.group(1) == expected.group(1)
