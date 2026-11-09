import math
from urllib.parse import unquote, urlparse

LOGO_SCALE_MIN = 50
LOGO_SCALE_MAX = 200


def normalize(value, *, general=False):
    if not isinstance(value, dict):
        raise ValueError("invalid_artwork")
    source = value.get("source")
    if source not in ("auto", "capsule", "header", "hero"):
        raise ValueError("invalid_source")
    image = value.get("image")
    if general and image is not None:
        raise ValueError("invalid_general_image")
    if image is not None:
        if not isinstance(image, str) or len(image) > 2048:
            raise ValueError("invalid_image")
        url = urlparse(image)
        path = unquote(url.path)
        if "\\" in path or any(part in (".", "..") for part in path.split("/")):
            raise ValueError("invalid_image")
        if url.scheme != "https" or url.netloc != "steamloopback.host" or not url.path.startswith(("/assets/", "/customimages/")):
            raise ValueError("invalid_image")
    result = {"source": source, "image": image}
    for key in ("positionX", "positionY"):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or not 0 <= number <= 100:
            raise ValueError("invalid_position")
        result[key] = number
    for key in ("showLogo", "showTitle"):
        if not isinstance(value.get(key), bool):
            raise ValueError("invalid_visibility")
        result[key] = value[key]
    # Optional; absent means 100%.
    if "logoScale" in value:
        scale = value["logoScale"]
        if isinstance(scale, bool) or not isinstance(scale, (float, int)) or not math.isfinite(scale) or not LOGO_SCALE_MIN <= scale <= LOGO_SCALE_MAX:
            raise ValueError("invalid_logo_scale")
        result["logoScale"] = scale
    # Optional logo position in percent of the cover; absent means centred (50).
    for key in ("logoPositionX", "logoPositionY"):
        if key in value:
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or not 0 <= number <= 100:
                raise ValueError("invalid_logo_position")
            result[key] = number
    return result


def records(value):
    out = {}
    if not isinstance(value, dict):
        return out
    for key, record in list(value.items())[:4096]:
        try:
            if isinstance(key, str) and key.isdecimal() and 0 <= int(key) < 2**32:
                out[str(int(key))] = normalize(record, general=int(key) == 0)
        except ValueError:
            continue
    return out
