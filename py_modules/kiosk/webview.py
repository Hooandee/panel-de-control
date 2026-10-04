"""Bottom screen browser: one WebKitGTK view, full screen; exits 3 when WebKitGTK is missing."""

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
            hardware_acceleration_policy=WebKit.HardwareAccelerationPolicy.ALWAYS,
        )
        context = WebKit.WebContext()
        context.set_cache_model(WebKit.CacheModel.DOCUMENT_VIEWER)
        view = WebKit.WebView(
            settings=settings,
            web_context=context,
            network_session=WebKit.NetworkSession.new_ephemeral(),
        )
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
