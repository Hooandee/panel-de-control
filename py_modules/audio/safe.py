from audio.const import GAIN_MAX

_GENERIC_BANDS = [3, 4, 6, 8, 9, 9, 8, 6, 5, 4]
_GENERIC_BASS = 60

_DEVICE: dict[str, dict] = {}


def band_ceilings(device_key):
    return list(_DEVICE.get(device_key, {}).get("bands", _GENERIC_BANDS))


def bass_ceiling(device_key):
    return int(_DEVICE.get(device_key, {}).get("bass", _GENERIC_BASS))


def safe_limits(device_key):
    return {"bands": band_ceilings(device_key), "bass": bass_ceiling(device_key)}


def clamp_gains(gains, ceilings):
    out = []
    for i, g in enumerate(gains):
        cap = ceilings[i] if i < len(ceilings) else GAIN_MAX
        try:
            out.append(min(float(g), float(cap)))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def clamp_bass(bass, ceiling):
    try:
        return min(int(bass), int(ceiling))
    except (TypeError, ValueError):
        return 0
