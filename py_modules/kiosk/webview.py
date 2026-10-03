"""Bottom screen browser: one WebKitGTK view, full screen, nothing else.

Runs under the system python (not the plugin's) inside the nested compositor that armada-run-bottom
starts. Next to a game that already fills the handheld's memory it costs a fraction of Firefox,
whose idle footprint (about 650 MB on the AYN Thor) pushed the game into swap and stuttered it.
Exits with status 3 when WebKitGTK is unavailable so the launcher can fall back to Firefox.
"""

import sys

UNAVAILABLE = 3


def main(url: str) -> int:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Gtk, WebKit
    except (ImportError, ValueError):
        return UNAVAILABLE

    def activate(app):
        settings = WebKit.Settings(
            enable_developer_extras=False,
            enable_back_forward_navigation_gestures=False,
            enable_page_cache=False,
            enable_smooth_scrolling=False,
            enable_webaudio=False,
            enable_webgl=False,
            enable_media=False,
            media_playback_requires_user_gesture=True,
            hardware_acceleration_policy=WebKit.HardwareAccelerationPolicy.NEVER,
        )
        view = WebKit.WebView(settings=settings)
        view.load_uri(url)
        window = Gtk.ApplicationWindow(application=app, decorated=False)
        window.set_child(view)
        window.fullscreen()
        window.present()

    app = Gtk.Application(application_id="org.paneldecontrol.BottomScreen")
    app.connect("activate", activate)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "about:blank"))
