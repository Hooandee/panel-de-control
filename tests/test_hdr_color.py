import math

import pytest

from display.hdr_color import build_hdr_cube, hdr_transform, pq_to_ictcp


def test_hdr_neutral_is_exact_identity():
    for point in (
        (0.0, 0.0, 0.0),
        (0.25, 0.5, 0.75),
        (1.0, 1.0, 1.0),
    ):
        assert hdr_transform(*point, saturation=100) == point


def test_hdr_saturation_preserves_ictcp_intensity_and_expands_chroma():
    before = pq_to_ictcp(0.6, 0.5, 0.4)
    output = hdr_transform(0.6, 0.5, 0.4, saturation=150)
    after = pq_to_ictcp(*output)

    assert after[0] == pytest.approx(before[0], abs=2e-5)
    assert math.hypot(after[1], after[2]) > math.hypot(
        before[1], before[2]
    )


def test_hdr_transform_clamps_only_the_final_encoded_output():
    output = hdr_transform(1.0, 0.0, 0.0, saturation=150)
    assert all(0.0 <= channel <= 1.0 for channel in output)


def test_hdr_out_of_gamut_boost_compresses_chroma_without_shifting_intensity():
    source = (0.7, 0.4, 0.2)
    base = pq_to_ictcp(*source)
    medium = pq_to_ictcp(*hdr_transform(*source, saturation=120))
    high = pq_to_ictcp(*hdr_transform(*source, saturation=150))

    assert medium[0] == pytest.approx(base[0], abs=2e-5)
    assert high[0] == pytest.approx(base[0], abs=2e-5)
    base_chroma = math.hypot(base[1], base[2])
    medium_chroma = math.hypot(medium[1], medium[2])
    high_chroma = math.hypot(high[1], high[2])
    assert medium_chroma + 1e-6 >= base_chroma
    assert high_chroma + 1e-6 >= medium_chroma


@pytest.mark.parametrize("source", [
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 1.0, 1.0),
    (1.0, 0.0, 1.0),
])
def test_boundary_colors_fall_back_to_valid_scale_one(source):
    output = hdr_transform(*source, saturation=150)
    assert output == pytest.approx(source, abs=3e-5)


def test_hdr_cube_has_33_nodes_per_axis_and_red_changes_fastest():
    cube = build_hdr_cube(100)
    lines = [line for line in cube.splitlines() if line[:1].isdigit()]

    assert "LUT_3D_SIZE 33" in cube
    assert len(lines) == 33 ** 3
    assert lines[0] == "0.000000 0.000000 0.000000"
    assert lines[1] == "0.031250 0.000000 0.000000"
    assert lines[-1] == "1.000000 1.000000 1.000000"
