"""Active output-route classification (speaker vs headphone/external). The EQ keeps an
independent curve per route; internal speakers get the correction, headphones/external
default to no speaker correction. Pure classifier + an injectable reader for testing."""

_HEADPHONE_HINTS = ("headphone", "headset", "bluetooth", "a2dp", "usb", "hdmi", "displayport")


def classify_route(name):
    """Map an output device/port description to our route. Defaults to 'speaker' (the
    built-in analog output) when nothing hints at an external device."""
    n = (name or "").lower()
    return "headphone" if any(h in n for h in _HEADPHONE_HINTS) else "speaker"


def route_of_default_sink(reader):
    """`reader()` returns the active output device/port description; classify it. Never
    raises — an unreadable audio stack falls back to 'speaker'."""
    try:
        return classify_route(reader())
    except Exception:
        return "speaker"
