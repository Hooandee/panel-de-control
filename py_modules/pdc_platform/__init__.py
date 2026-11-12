from . import anatase_hhd


_FIRST_CLASS = frozenset({"anatase", "bazzite", "cachyos", "steamos"})


def describe(os_id: str | None) -> dict:
    return {
        "id": os_id,
        "support_tier": "first-class" if os_id in _FIRST_CLASS else "capability",
    }


def select_hhd_tdp_client(os_id: str | None, default_client):
    return anatase_hhd if os_id == "anatase" else default_client
