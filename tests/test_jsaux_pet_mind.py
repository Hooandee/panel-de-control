import random

import pytest

from accessories.jsaux_pixel.scenes import pet_mind
from accessories.jsaux_pixel.scenes.pet_mind import Mind

HOUR = 3600.0


def _mind(tmp_path, now=1_000_000.0, seed=1):
    return Mind(tmp_path / "pet.json", clock=lambda: now, rng=random.Random(seed))


def test_a_new_pet_is_born_content_with_a_personality(tmp_path):
    mind = _mind(tmp_path)
    needs = mind.needs(1_000_000.0)
    assert all(value >= 0.9 for value in needs.values())
    assert set(mind.traits) == set(pet_mind.TRAITS)
    assert all(0.0 <= value <= 1.0 for value in mind.traits.values())


def test_the_personality_and_memories_survive_a_restart(tmp_path):
    mind = _mind(tmp_path)
    mind.interact("feed", 1_000_000.0 + 5 * HOUR)
    again = _mind(tmp_path, seed=99)
    assert again.traits == mind.traits
    assert again.memory["fed_at"] == 1_000_000.0 + 5 * HOUR


def test_needs_drift_with_real_time_and_care_restores_them(tmp_path):
    mind = _mind(tmp_path)
    later = 1_000_000.0 + 7 * HOUR
    hungry = mind.needs(later)
    assert hungry["hunger"] < 0.3
    assert hungry["fun"] < 0.3
    assert mind.interact("feed", later) == "eat"
    assert mind.needs(later)["hunger"] == pytest.approx(1.0)
    assert mind.interact("play", later) == "play"
    assert mind.needs(later)["fun"] > 0.9
    assert mind.interact("pet", later) == "purr"
    assert mind.needs(later)["love"] > 0.9


def test_a_full_pet_turns_food_down(tmp_path):
    mind = _mind(tmp_path)
    assert mind.interact("feed", 1_000_000.0 + 60) == "refuse"


def test_sleep_restores_energy(tmp_path):
    mind = _mind(tmp_path)
    evening = mind.needs(1_000_000.0 + 15 * HOUR)["energy"]
    assert evening < 0.3
    mind.interact("sleep", 1_000_000.0 + 15 * HOUR)
    assert mind.needs(1_000_000.0 + 23 * HOUR)["energy"] > 0.9


def test_unknown_interactions_are_refused(tmp_path):
    with pytest.raises(ValueError):
        _mind(tmp_path).interact("hack", 1_000_000.0)


@pytest.mark.parametrize("tags,genre", [
    ([4145, 1742, 1667, 19], "horror"),
    ([699, 19], "racing"),
    ([4182, 3814, 1774], "shooter"),
    ([122, 4434], "rpg"),
    ([1664], "puzzle"),
    ([4726, 597], "cozy"),
    ([492, 4182], None),
])
def test_games_are_read_by_their_top_store_tags(tags, genre):
    assert pet_mind.genre_for(tags) == genre


def test_scary_games_scare_less_with_practice(tmp_path):
    mind = _mind(tmp_path)
    first = mind.fear("horror")
    for i in range(6):
        mind.saw_game(str(i), "horror", 1_000_000.0 + i)
    assert mind.fear("horror") < first
    assert mind.fear("cozy") == 0.0


def test_the_favourite_genre_is_the_one_played_most(tmp_path):
    mind = _mind(tmp_path)
    mind.saw_game("1", "racing", 1_000_000.0)
    mind.saw_game("2", "rpg", 1_000_100.0)
    mind.saw_game("3", "racing", 1_000_200.0)
    assert mind.favourite() == "racing"


def test_seeing_the_same_session_twice_counts_once(tmp_path):
    mind = _mind(tmp_path)
    mind.saw_game("1", "racing", 1_000_000.0)
    mind.saw_game("1", "racing", 1_000_000.0)
    assert mind.memory["genres"]["racing"] == 1


def test_the_plan_answers_needs_and_never_repeats_back_to_back(tmp_path):
    mind = _mind(tmp_path)
    plan = mind.plan(1_000_000.0 + 7 * HOUR, 600, situation="home", rng=random.Random(3))
    names = [name for name, _rest in plan]
    assert any(name in ("snack", "hungry") for name in names)
    assert all(a != b for a, b in zip(names, names[1:]))
    assert all(name in pet_mind.ACTIONS for name in names)
    assert sum(rest for _name, rest in plan) <= 600


def test_the_plan_is_the_same_for_the_same_moment(tmp_path):
    mind = _mind(tmp_path)
    a = mind.plan(1_000_000.0 + HOUR, 600, situation="home", rng=random.Random(5))
    b = mind.plan(1_000_000.0 + HOUR, 600, situation="home", rng=random.Random(5))
    assert a == b


def test_a_lonely_pet_asks_for_attention(tmp_path):
    mind = _mind(tmp_path)
    plan = mind.plan(1_000_000.0 + 30 * HOUR, 600, situation="home", rng=random.Random(4))
    assert any(name in ("call", "sulk") for name, _ in plan)


def test_planning_never_changes_the_memory(tmp_path):
    mind = _mind(tmp_path)
    before = dict(mind.memory)
    mind.plan(1_000_000.0 + 7 * HOUR, 600, situation="game:racing", rng=random.Random(1))
    assert mind.memory == before


def test_while_playing_it_does_game_things(tmp_path):
    mind = _mind(tmp_path)
    plan = mind.plan(1_000_000.0 + HOUR, 600, situation="game:racing", rng=random.Random(2))
    names = {name for name, _ in plan}
    assert names & {"zoom", "watch", "cheer"}
    assert not names & {"nap", "snack", "peekaboo"}


def test_a_corrupt_store_starts_a_fresh_pet(tmp_path):
    (tmp_path / "pet.json").write_text("{nope")
    assert _mind(tmp_path).needs(1_000_000.0)["hunger"] > 0.9


def test_a_rename_is_kept_short_and_clean(tmp_path):
    mind = _mind(tmp_path)
    mind.rename("  Pixi la mascota más bonita  ")
    assert mind.memory["name"] == "Pixi la mascota"
    mind.rename("")
    assert mind.memory["name"] == "Pixi la mascota"


MONDAY_21 = 0 * 24 + 21


def _play(mind, start, minutes, hour_of_week, step=5.0):
    t = start
    while t < start + minutes * 60:
        mind.observe(t, night=False, playing=True, hour_of_week=hour_of_week)
        t += step
    return t


def test_it_learns_when_you_usually_play(tmp_path):
    mind = _mind(tmp_path)
    week = 7 * 86400
    for k in range(3):
        _play(mind, 1_000_000.0 + k * week, 60, MONDAY_21)
    later = 1_000_000.0 + 3 * week
    assert mind.expectation(MONDAY_21, later) > 0.8
    assert mind.expectation(1 * 24 + 10, later) == 0.0
    assert mind.describe(later)["usual_hours"] == [21, 22]


def test_one_evening_is_not_a_habit(tmp_path):
    mind = _mind(tmp_path)
    _play(mind, 1_000_000.0, 40, MONDAY_21)
    assert mind.expectation(MONDAY_21, 1_000_000.0 + 3600) == 0.0


def test_an_old_habit_fades(tmp_path):
    mind = _mind(tmp_path)
    week = 7 * 86400
    for k in range(3):
        _play(mind, 1_000_000.0 + k * week, 60, MONDAY_21)
    assert mind.expectation(MONDAY_21, 1_000_000.0 + 12 * week) == 0.0


def test_learning_saves_at_most_every_few_minutes(tmp_path, monkeypatch):
    mind = _mind(tmp_path)
    saves = []
    monkeypatch.setattr(mind, "_save", lambda: saves.append(1))
    _play(mind, 1_000_000.0, 60, MONDAY_21, step=1.0)
    assert len(saves) <= 8


def test_the_habit_survives_a_restart(tmp_path):
    mind = _mind(tmp_path)
    week = 7 * 86400
    for k in range(3):
        _play(mind, 1_000_000.0 + k * week, 60, MONDAY_21)
    again = _mind(tmp_path)
    assert again.expectation(MONDAY_21, 1_000_000.0 + 3 * week) > 0.8


def test_at_the_usual_hour_it_waits_for_you(tmp_path):
    mind = _mind(tmp_path)
    plan = mind.plan(1_000_000.0 + 600, 600, situation="home", rng=random.Random(3), expect=1.0)
    assert "await" in {name for name, _ in plan}
    calm = mind.plan(1_000_000.0 + 600, 600, situation="home", rng=random.Random(3), expect=0.0)
    assert "await" not in {name for name, _ in calm}


def test_when_the_console_sleeps_the_pet_sleeps_too(tmp_path):
    mind = _mind(tmp_path)
    start = 1_000_000.0
    mind.observe(start, night=False, playing=False)
    mind.observe(start + 9 * HOUR, night=False, playing=False)
    needs = mind.needs(start + 9 * HOUR)
    assert needs["energy"] > 0.9
    assert not mind.asleep()


def test_needs_drop_slower_while_it_sleeps(tmp_path):
    mind = _mind(tmp_path)
    start = 1_000_000.0
    mind.observe(start, night=True, playing=False)
    mind.observe(start + 8 * HOUR, night=False, playing=False)
    needs = mind.needs(start + 8 * HOUR)
    assert needs["hunger"] >= 0.45
    assert needs["fun"] > 0.9
    assert needs["love"] > 0.6


def test_a_restart_remembers_when_it_last_saw_the_console(tmp_path):
    mind = _mind(tmp_path)
    mind.observe(1_000_000.0, night=False, playing=False)
    again = _mind(tmp_path)
    again.observe(1_000_000.0 + 9 * HOUR, night=False, playing=False)
    assert again.needs(1_000_000.0 + 9 * HOUR)["energy"] > 0.9


def test_nullable_memory_survives_a_reload(tmp_path):
    path = tmp_path / "pet.json"
    mind = Mind(path)
    mind.memory.update({"asleep_since": 1_000_000.0, "last_session": "42:123", "proud_at": 5.0, "interaction": ["trophy", 6.0]})
    mind._save()
    again = Mind(path)
    assert again.memory["asleep_since"] == 1_000_000.0
    assert again.memory["last_session"] == "42:123"
    assert again.memory["proud_at"] == 5.0
    assert again.memory["interaction"] == ["trophy", 6.0]
