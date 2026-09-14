import json

import auto_tdp_learning
from auto_tdp_learning import AutoTdpLearningStore


def store(tmp_path, required=4):
    return AutoTdpLearningStore(
        str(tmp_path / "auto_tdp_learning.json"),
        required_samples=required,
    )


def test_learning_isolated_by_game_target_and_power_source(tmp_path):
    learned = store(tmp_path, required=1)
    learned.record("42", 57, False, 14, stable=True)
    learned.record("42", 58, False, 20, stable=True)
    learned.record("42", 57, True, 18, stable=True)

    assert learned.seed("42", 57, False, 5, 35)["watts"] == 14
    assert learned.seed("42", 58, False, 5, 35)["watts"] == 20
    assert learned.seed("42", 57, True, 5, 35)["watts"] == 18


def test_unstable_or_insufficient_observations_never_become_a_seed(tmp_path):
    learned = store(tmp_path, required=3)
    learned.record("42", 40, False, 8, stable=False)
    learned.record("42", 40, False, 14, stable=True)
    learned.record("42", 40, False, 15, stable=True)

    assert learned.seed("42", 40, False, 5, 35) is None


def test_stable_history_returns_bounded_median_and_confidence(tmp_path):
    learned = store(tmp_path, required=4)
    for watts in (14, 15, 14, 14):
        learned.record("42", 40, False, watts, stable=True)

    assert learned.seed("42", 40, False, 5, 35) == {
        "watts": 14,
        "samples": 4,
        "confidence": 0.25,
    }

    learned.reset()
    for _ in range(4):
        learned.record("42", 40, False, 80, stable=True)
    assert learned.seed("42", 40, False, 5, 35)["watts"] == 35


def test_learning_survives_reload_and_reset_only_clears_its_store(tmp_path):
    path = str(tmp_path / "auto_tdp_learning.json")
    first = AutoTdpLearningStore(path, required_samples=1)
    first.record("42", 45, False, 16, stable=True)

    second = AutoTdpLearningStore(path, required_samples=1)
    assert second.seed("42", 45, False, 5, 35)["watts"] == 16
    second.reset()
    assert AutoTdpLearningStore(path, required_samples=1).seed(
        "42", 45, False, 5, 35
    ) is None


def test_corrupt_json_recovers_as_empty_without_raising(tmp_path):
    path = tmp_path / "auto_tdp_learning.json"
    path.write_text("{not-json", encoding="utf-8")

    learned = AutoTdpLearningStore(str(path), required_samples=1)

    assert learned.seed("42", 40, False, 5, 35) is None
    learned.record("42", 40, False, 15, stable=True)
    assert json.loads(path.read_text(encoding="utf-8"))["profiles"]


def test_learning_history_is_timestamped_and_profile_count_is_bounded(tmp_path):
    clock = iter((10.0, 20.0, 30.0))
    learned = AutoTdpLearningStore(
        str(tmp_path / "auto_tdp_learning.json"),
        required_samples=1,
        max_profiles=2,
        clock=lambda: next(clock),
    )

    learned.record("1", 40, False, 10, stable=True)
    learned.record("2", 40, False, 11, stable=True)
    learned.record("3", 40, False, 12, stable=True)

    saved = json.loads(
        (tmp_path / "auto_tdp_learning.json").read_text(encoding="utf-8")
    )
    assert saved["version"] == 2
    assert set(saved["profiles"]) == {"2:40:battery", "3:40:battery"}
    assert saved["profiles"]["3:40:battery"]["samples"] == [
        {"watts": 12, "at": 30.0}
    ]


def test_failed_persistence_does_not_pollute_in_memory_learning(
    tmp_path, monkeypatch
):
    learned = store(tmp_path, required=1)
    monkeypatch.setattr(
        auto_tdp_learning,
        "atomic_json_save",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert learned.record("42", 40, False, 14, stable=True) is False
    assert learned.seed("42", 40, False, 5, 35) is None
