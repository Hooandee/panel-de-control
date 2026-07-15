"""Active output-route classification (speaker vs headphone/external). The EQ keeps an
independent curve per route; internal speakers get the correction, headphones/external
default to no speaker correction. Pure classifier + an injectable reader for testing."""

_HEADPHONE_HINTS = ("headphone", "headset", "bluetooth", "a2dp", "usb", "hdmi", "displayport")


def classify_route(name):
    """Map an output device/port description to our route. Defaults to 'speaker' (the
    built-in analog output) when nothing hints at an external device."""
    n = (name or "").lower()
    return "headphone" if any(h in n for h in _HEADPHONE_HINTS) else "speaker"


def route_of_sink(pactl_list_output, sink_name):
    if sink_name:
        in_block = False
        for line in (pactl_list_output or "").splitlines():
            s = line.strip()
            if s.startswith("Name:"):
                in_block = s.split("Name:", 1)[1].strip() == sink_name
            elif in_block and s.startswith("Active Port:"):
                return classify_route(s)
    return "speaker"
