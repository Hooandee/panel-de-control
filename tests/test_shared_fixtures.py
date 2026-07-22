import json
from pathlib import Path

from auto_tdp import decide
from fans.suggest import band, biased_curve, enough_data, suggest_curves
from tdp.suggest import learned_band
from telemetry.store import TelemetryStore


FIXTURE_DIR = Path(__file__).parents[1] / "shared" / "fixtures"
EXPECTED_FIXTURES = {
    "auto_tdp.json",
    "fan_suggestions.json",
    "tdp_learned_band.json",
    "telemetry_learning.json",
}


def _normalized(value):
    if isinstance(value, dict):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _load_documents():
    return [json.loads(path.read_text()) for path in sorted(FIXTURE_DIR.glob("*.json"))]


def _run_case(document, case, tmp_path):
    operation = document["algorithm"]
    inputs = case["input"]

    if operation == "auto_tdp.decide":
        result = decide(
            inputs["current_pl1"],
            inputs["gpu_window"],
            inputs["slack_ticks"],
            inputs["min_w"],
            inputs["max_w"],
            up_step=inputs.get("up_step", 2),
            down_step=inputs.get("down_step", 1),
            max_down_step=inputs.get("max_down_step", 5),
        )
        return {"next_pl1": result[0], "slack_ticks": result[1]}

    if operation == "tdp.suggest.learned_band":
        return learned_band(inputs["by_pl1"])

    if operation == "fans.suggest":
        histogram = {int(key): value for key, value in inputs.get("histogram", {}).items()}
        action = case["operation"]
        if action == "enough_data":
            ok, reason = enough_data(histogram)
            return {"ok": ok, "reason": reason}
        if action == "band":
            return band(histogram)
        curves = suggest_curves(band(histogram))
        if action == "suggest_curves":
            return curves
        if action == "biased_curve":
            return biased_curve(curves, inputs["bias"])

    if operation == "telemetry.store":
        store = TelemetryStore(str(tmp_path / f"{case['id']}.json"))
        for item in inputs["samples"]:
            store.add_sample(
                inputs["appid"],
                item["sample"],
                dt=item.get("dt", 5.0),
                ts=item.get("ts", 0.0),
            )
        return {
            "aggregate": store.aggregate(inputs["appid"]),
            "temp_histogram": store.temp_histogram(inputs["appid"]),
        }

    raise AssertionError(f"unsupported fixture operation: {operation}")


def test_shared_fixture_catalog_is_complete():
    assert FIXTURE_DIR.is_dir()
    assert {path.name for path in FIXTURE_DIR.glob("*.json")} == EXPECTED_FIXTURES


def test_current_python_brain_matches_shared_fixtures(tmp_path):
    documents = _load_documents()
    assert documents
    for document in documents:
        assert document["schema_version"] == 1
        assert document["cases"]
        for case in document["cases"]:
            actual = _normalized(_run_case(document, case, tmp_path))
            assert actual == _normalized(case["expected"]), case["id"]
