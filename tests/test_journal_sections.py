import asyncio
import re
import sys
from pathlib import Path

from journal_context import bounded, pick_fields, section_changes
from test_tdp_guard_rpc import plugin  # noqa: F401

REGISTRY = Path(__file__).resolve().parents[1] / "src" / "sections" / "registry.tsx"


def _panel_sections():
    source = REGISTRY.read_text()
    block = source[source.index("const COMPONENTS"):]
    block = block[:block.index("};")]
    return set(re.findall(r"^\s+([a-z_]+):", block, re.M))


def test_every_panel_section_declares_what_it_has_applied(plugin):  # noqa: F811
    main = sys.modules["main"]
    sections = _panel_sections()
    assert sections, "registry.tsx changed shape; update this test"
    assert sections == set(main._SUPPORT_SECTIONS), (
        "Every Panel section needs support logs: add it to main._SUPPORT_SECTIONS"
    )


def test_every_declared_source_exists_on_the_plugin(plugin):  # noqa: F811
    main = sys.modules["main"]
    for section, sources in main._SUPPORT_SECTIONS.items():
        for getter, _fields in sources:
            assert callable(getattr(main.Plugin, getter, None)), f"{section}: {getter} is missing"


def test_section_states_are_collected_for_every_section(plugin):  # noqa: F811
    main = sys.modules["main"]
    states = asyncio.run(plugin._support_section_states())
    assert set(states) == set(main._SUPPORT_SECTIONS)
    assert all(isinstance(state, dict) for state in states.values())
    assert set(states["system"]) == {"cpu_state", "gpu_clock", "eco_state", "battery_state"}


def test_pick_fields_reaches_nested_values_and_skips_missing():
    value = {"a": 1, "model": {"layout": "vertical", "items": [1, 2]}, "live": 33}
    assert pick_fields(value, ("a", "model.layout", "nope")) == {"a": 1, "model.layout": "vertical"}
    assert pick_fields(value, None) is value


def test_only_changed_sections_are_written_again():
    first = {"hud": {"enabled": True}, "fans": {"preset": "auto"}}
    assert section_changes(None, first) == first
    assert section_changes(first, first) == {}
    assert section_changes(first, {**first, "fans": {"preset": "quiet"}}) == {"fans": {"preset": "quiet"}}


def test_an_oversized_summary_is_cut_to_one_line():
    assert "truncated" in bounded({"items": ["x" * 50] * 100})


def test_internal_counters_never_look_like_a_change(plugin, monkeypatch):  # noqa: F811
    counter = iter(range(100))

    async def battery():
        return {"charge_limit": {"enabled": False, "reconciliation": {"generation": next(counter), "history": [1]}}}

    monkeypatch.setattr(plugin, "get_battery_state", battery)
    first = asyncio.run(plugin._support_section_states())["system"]
    second = asyncio.run(plugin._support_section_states())["system"]
    assert first == second
