"""Active output-route classification (speaker vs headphone/external). The EQ keeps an
independent curve per route; internal speakers get the correction, headphones/external
default to no speaker correction. Pure classifier + an injectable reader for testing."""

_HEADPHONE_HINTS = (
    "headphone",
    "headset",
    "bluetooth",
    "bluez_output",
    "a2dp",
    "usb",
    "hdmi",
    "displayport",
)


def classify_route(name):
    """Map an output device/port description to our route. Defaults to 'speaker' (the
    built-in analog output) when nothing hints at an external device."""
    n = (name or "").lower()
    return "headphone" if any(h in n for h in _HEADPHONE_HINTS) else "speaker"


def route_of_sink(pactl_list_output, sink_name):
    if not sink_name:
        return "speaker"
    in_block = False
    description = ""
    active_port = ""
    for line in (pactl_list_output or "").splitlines():
        s = line.strip()
        if s.startswith("Name:"):
            if in_block:
                break
            in_block = s.split("Name:", 1)[1].strip() == sink_name
        elif in_block and s.startswith("Description:"):
            description = s.split("Description:", 1)[1].strip()
        elif in_block and s.startswith("Active Port:"):
            active_port = s.split("Active Port:", 1)[1].strip()
    if in_block:
        return classify_route(f"{sink_name} {description} {active_port}")
    return "speaker"
