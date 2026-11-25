from __future__ import annotations

import os
from typing import Iterable, Optional

from .media_types import is_list_file, media_kind


def resolve_servable(path: str, roots: Iterable[str]) -> Optional[str]:
    """Return the real path only when it is a supported media file inside a registered root.

    Symlinks are resolved before the containment check so a link cannot escape its root.
    """
    real = os.path.realpath(path)
    if not os.path.isfile(real) or media_kind(real) is None:
        return None
    for root in roots:
        real_root = os.path.realpath(root)
        if os.path.commonpath([real, real_root]) == real_root and real != real_root:
            return real
    return None


def resolve_list(path: str, roots: Iterable[str]) -> Optional[tuple[str, str]]:
    """The real path of an .m3u/.m3u8 and the registered root that holds it, or None.

    Same containment rule as media: symlinks are resolved first so a list cannot be a link out of its root.
    """
    real = os.path.realpath(path)
    if not os.path.isfile(real) or not is_list_file(real):
        return None
    for root in roots:
        real_root = os.path.realpath(root)
        if os.path.commonpath([real, real_root]) == real_root and real != real_root:
            return real, real_root
    return None
