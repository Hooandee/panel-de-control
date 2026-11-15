import asyncio
import json
import sys
from pathlib import Path

from journal_context import bounded, section_changes
from journal_context import pick_fields

PANEL_SECTIONS = Path(__file__).resolve().parents[1] / "shared" / "contracts" / "panel-sections.json"


def test_every_panel_section_declares_what_it_has_applied(plugin):  # noqa: F811
    main = sys.modules["main"]
    sections = json.loads(PANEL_SECTIONS.read_text())
    assert set(sections) == set(main._SUPPORT_SECTIONS), (
        "Every Panel section needs support logs: add it to main._SUPPORT_SECTIONS"
    )


def test_every_declared_source_exists_on_the_plugin(plugin):  # noqa: F811
    main = sys.modules["main"]
    for section, sources in main._SUPPORT_SECTIONS.items():
        for getter, _fields in sources:
            assert callable(getattr(main.Plugin, getter, None)), f"{section}: {getter} is missing"


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


def test_pick_fields_reaches_nested_values_and_skips_missing():
    value = {"a": 1, "model": {"layout": "vertical", "items": [1, 2]}, "live": 33}
    assert pick_fields(value, ("a", "model.layout", "nope")) == {"a": 1, "model.layout": "vertical"}
    assert pick_fields(value, None) is value
