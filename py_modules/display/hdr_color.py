"""BT.2100 PQ/ICtCp saturation transform for gamescope's HDR look LUT."""

import math
from functools import lru_cache


_PQ_M1 = 2610 / 16384
_PQ_M2 = 2523 / 32
_PQ_C1 = 3424 / 4096
_PQ_C2 = 2413 / 128
_PQ_C3 = 2392 / 128
_HDR_LUT_SIZE = 33

_RGB_TO_LMS = (
    (1688 / 4096, 2146 / 4096, 262 / 4096),
    (683 / 4096, 2951 / 4096, 462 / 4096),
    (99 / 4096, 309 / 4096, 3688 / 4096),
)
_LMS_TO_RGB = (
    (3.436606694333, -2.506452118656, 0.069845424323),
    (-0.791329555599, 1.983600451792, -0.192270896193),
    (-0.025949899691, -0.098913714712, 1.124863614402),
)
_LMS_P_TO_ICTCP = (
    (0.5, 0.5, 0.0),
    (6610 / 4096, -13613 / 4096, 7003 / 4096),
    (17933 / 4096, -17390 / 4096, -543 / 4096),
)
_ICTCP_TO_LMS_P = (
    (1.0, 0.008609037038, 0.111029625003),
    (1.0, -0.008609037038, -0.111029625003),
    (1.0, 0.560031335711, -0.320627174987),
)


def _matmul(matrix, values):
    return tuple(
        sum(coefficient * value for coefficient, value in zip(row, values))
        for row in matrix
    )


def _pq_decode(value):
    power = value ** (1 / _PQ_M2)
    numerator = max(power - _PQ_C1, 0.0)
    denominator = _PQ_C2 - _PQ_C3 * power
    return (numerator / denominator) ** (1 / _PQ_M1)


def _pq_encode(value):
    power = value ** _PQ_M1
    return ((_PQ_C1 + _PQ_C2 * power) / (1 + _PQ_C3 * power)) ** _PQ_M2


def _signed_pq_decode(value):
    return math.copysign(_pq_decode(abs(value)), value)


def _signed_pq_encode(value):
    return math.copysign(_pq_encode(abs(value)), value)


def _clamp01(value):
    return min(1.0, max(0.0, value))


def pq_to_ictcp(red, green, blue):
    linear_rgb = tuple(_pq_decode(channel) for channel in (red, green, blue))
    linear_lms = _matmul(_RGB_TO_LMS, linear_rgb)
    encoded_lms = tuple(_signed_pq_encode(value) for value in linear_lms)
    return _matmul(_LMS_P_TO_ICTCP, encoded_lms)


def _ictcp_to_linear_rgb(intensity, chroma_t, chroma_p):
    encoded_lms = _matmul(
        _ICTCP_TO_LMS_P, (intensity, chroma_t, chroma_p)
    )
    linear_lms = tuple(_signed_pq_decode(value) for value in encoded_lms)
    return _matmul(_LMS_TO_RGB, linear_lms)


def _linear_rgb_to_pq(linear_rgb):
    encoded_rgb = tuple(_signed_pq_encode(value) for value in linear_rgb)
    return tuple(_clamp01(value) for value in encoded_rgb)


def _in_gamut(linear_rgb):
    return all(
        math.isfinite(value) and -1e-12 <= value <= 1.0 + 1e-12
        for value in linear_rgb
    )


def hdr_transform(red, green, blue, saturation=100):
    if saturation == 100:
        return red, green, blue
    intensity, chroma_t, chroma_p = pq_to_ictcp(red, green, blue)
    scale = saturation / 100
    linear_rgb = _ictcp_to_linear_rgb(
        intensity, chroma_t * scale, chroma_p * scale
    )
    if scale > 1.0 and not _in_gamut(linear_rgb):
        linear_rgb = _ictcp_to_linear_rgb(
            intensity, chroma_t, chroma_p
        )
        lower, upper = 1.0, scale
        for _ in range(18):
            candidate = (lower + upper) / 2
            candidate_rgb = _ictcp_to_linear_rgb(
                intensity,
                chroma_t * candidate,
                chroma_p * candidate,
            )
            if _in_gamut(candidate_rgb):
                lower, linear_rgb = candidate, candidate_rgb
            else:
                upper = candidate
    return _linear_rgb_to_pq(linear_rgb)


@lru_cache(maxsize=12)
def build_hdr_cube(saturation, size=_HDR_LUT_SIZE):
    denominator = size - 1
    lines = ['TITLE "panel-de-control HDR"', f"LUT_3D_SIZE {size}"]
    for blue_index in range(size):
        for green_index in range(size):
            for red_index in range(size):
                output = hdr_transform(
                    red_index / denominator,
                    green_index / denominator,
                    blue_index / denominator,
                    saturation,
                )
                lines.append(" ".join(f"{channel:.6f}" for channel in output))
    return "\n".join(lines) + "\n"
