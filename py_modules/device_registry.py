from device_profiles import DEVICE_TABLE, GENERIC, DeviceProfile

_DMI_PRODUCT = "/sys/class/dmi/id/product_name"


def _read_product_name() -> str:
    try:
        with open(_DMI_PRODUCT) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def detect(product_name: str | None = None) -> DeviceProfile:
    """Return the DeviceProfile for this machine. Never raises. Falls back to GENERIC.
    `product_name` is injectable for tests; in production it reads DMI."""
    name = product_name if product_name is not None else _read_product_name()
    lname = name.lower()
    for profile in DEVICE_TABLE:
        for needle in profile.match_names:
            if needle.lower() in lname:
                return profile
    return GENERIC
