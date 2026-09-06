from controllers.ayaneo3 import (
    HhdMagicModules,
)


def _hhd_state(left="Cross / Joystick", right=r"ABXY \ Joystick"):
    return {
        "magic_modules": {
            "magic_modules": {
                "pop_left": False,
                "pop_right": False,
                "pop_both": False,
                "info_left": left,
                "info_right": right,
            }
        }
    }


def test_bazzite_43_hhd_contract_posts_once_and_requires_disconnected_state():
    states = iter((
        _hhd_state(),
        _hhd_state(left="Ejecting..."),
        _hhd_state(left="Disconnected"),
    ))
    posts = []
    backend = HhdMagicModules(
        read_state=lambda: next(states),
        post_state=lambda payload: posts.append(payload) or _hhd_state(left="Ejecting..."),
        sleep=lambda _seconds: None,
        polls=3,
    )

    result = backend.run("eject_left")

    assert posts == [{"magic_modules": {"magic_modules": {"pop_left": True}}}]
    assert result["outcome"] == "confirmed"
    assert result["accepted"] is True
    assert result["modules"]["left"] == "disconnected"


def test_hhd_action_consumed_without_disconnect_is_unverifiable_not_success():
    posts = []
    backend = HhdMagicModules(
        read_state=lambda: _hhd_state(),
        post_state=lambda payload: posts.append(payload) or _hhd_state(),
        sleep=lambda _seconds: None,
        polls=2,
    )

    result = backend.run("eject_right")

    assert len(posts) == 1
    assert result["outcome"] == "unverifiable"
    assert result["accepted"] is True


def test_hhd_tree_absent_never_posts_an_action():
    posts = []
    backend = HhdMagicModules(
        read_state=lambda: {"controllers": {}},
        post_state=lambda payload: posts.append(payload),
        sleep=lambda _seconds: None,
    )

    result = backend.run("eject_both")

    assert result["outcome"] == "unavailable"
    assert result["accepted"] is None
    assert posts == []


def test_unknown_hhd_module_label_fails_closed_and_never_posts():
    for label in ("Unknown", "Future module label"):
        posts = []
        backend = HhdMagicModules(
            read_state=lambda: _hhd_state(left=label),
            post_state=lambda payload: posts.append(payload),
        )

        result = backend.run("eject_left")

        assert result["outcome"] == "unavailable"
        assert result["modules"]["left"] == "unknown"
        assert posts == []


def test_hhd_action_schema_must_publish_all_three_actions():
    state = _hhd_state()
    del state["magic_modules"]["magic_modules"]["pop_both"]
    posts = []
    backend = HhdMagicModules(
        read_state=lambda: state,
        post_state=lambda payload: posts.append(payload),
    )

    assert backend.state()["supported"] is False
    assert backend.run("eject_left")["outcome"] == "unavailable"
    assert posts == []


def test_lost_hhd_post_response_is_unverifiable_and_never_retried():
    posts = []
    backend = HhdMagicModules(
        read_state=lambda: _hhd_state(),
        post_state=lambda payload: posts.append(payload),
        sleep=lambda _seconds: None,
        polls=2,
    )

    result = backend.run("eject_left")

    assert result["outcome"] == "unverifiable"
    assert result["accepted"] is None
    assert len(posts) == 1


def test_hhd_polling_obeys_a_total_deadline_even_when_state_never_changes():
    now = [0.0]
    reads = []

    def sleep(seconds):
        now[0] += seconds

    backend = HhdMagicModules(
        read_state=lambda: reads.append(now[0]) or _hhd_state(),
        post_state=lambda _payload: _hhd_state(),
        sleep=sleep,
        monotonic=lambda: now[0],
        polls=100,
        deadline_s=0.7,
    )

    result = backend.run("eject_left")

    assert result["outcome"] == "unverifiable"
    assert now[0] <= 0.7
    assert len(reads) < 10
