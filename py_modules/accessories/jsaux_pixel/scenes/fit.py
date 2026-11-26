"""Whether a segment encodes within the panel's GIF size limit."""

from .. import codec, gif
from ..render.canvas import quantize
from .base import Segment


def encoded_size(segment: Segment) -> int:
    palette, indexed = quantize(segment.frames)
    return len(gif.encode([gif.Frame(px, d) for px, d in zip(indexed, segment.delays_cs)], palette))


def fits(segment: Segment) -> bool:
    return encoded_size(segment) <= codec.MAX_GIF_BYTES
