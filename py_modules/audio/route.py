"""Active output-route classification (speaker vs headphone/external). The EQ keeps an
independent curve per route; internal speakers get the correction, headphones/external
default to no speaker correction. Pure classifier + an injectable reader for testing."""

_HEADPHONE_HINTS = ("headphone", "headset", "bluetooth", "a2dp", "usb", "hdmi", "displayport")


def classify_route(name):
    """Map an output device/port description to our route. Defaults to 'speaker' (the
    built-in analog output) when nothing hints at an external device."""
    n = (name or "").lower()
    return "headphone" if any(h in n for h in _HEADPHONE_HINTS) else "speaker"


def route_from_sinks(pactl_list_output):
    """Classify the active output route from `pactl list sinks` text. The physical sink
    exposes an ``Active Port:`` (e.g. analog-output-headphones / analog-output-speaker);
    our virtual EQ sink has none, so the only Active Port is the real device's. Defaults
    to 'speaker' when no active port is found."""
    for line in (pactl_list_output or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Active Port:"):
            return classify_route(stripped)
    return "speaker"


def route_of_sink(pactl_list_output, sink_name):
    """Classify the active port of a specific sink. On multi-sink devices (Intel HDA exposes
    HDMI1/2/3 alongside the speaker) the first Active Port isn't the real output, so classify
    the sink we actually feed. Falls back to the first active port when it isn't found."""
    if sink_name:
        in_block = False
        for line in (pactl_list_output or "").splitlines():
            s = line.strip()
            if s.startswith("Name:"):
                in_block = s.split("Name:", 1)[1].strip() == sink_name
            elif in_block and s.startswith("Active Port:"):
                return classify_route(s)
    return route_from_sinks(pactl_list_output)


def route_of_default_sink(reader):
    """`reader()` returns `pactl list sinks` text; classify the active port. Never raises
    — an unreadable audio stack falls back to 'speaker'."""
    try:
        return route_from_sinks(reader())
    except Exception:
        return "speaker"
