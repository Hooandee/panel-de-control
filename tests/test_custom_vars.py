from launch.custom_vars import coerce_custom_vars


def test_valid_list_passes_through():
    raw = [
        {"id": "a", "name": "FPS", "kind": "env", "envName": "DXVK_FRAME_RATE", "envValue": "60"},
        {"id": "b", "name": "No joy", "kind": "arg", "arg": "-nojoy"},
    ]
    assert coerce_custom_vars(raw) == raw


def test_non_list_yields_empty():
    assert coerce_custom_vars(None) == []
    assert coerce_custom_vars("garbage") == []
    assert coerce_custom_vars({"id": "a"}) == []


def test_drops_entries_missing_id_or_name():
    raw = [
        {"name": "x", "kind": "arg", "arg": "-x"},               # no id
        {"id": "y", "kind": "arg", "arg": "-y"},                 # no name
        {"id": "z", "name": "  ", "kind": "arg", "arg": "-z"},   # blank name
    ]
    assert coerce_custom_vars(raw) == []


def test_env_requires_valid_name():
    raw = [
        {"id": "a", "name": "ok", "kind": "env", "envName": "GOOD_NAME", "envValue": "1"},
        {"id": "b", "name": "bad", "kind": "env", "envName": "1BAD", "envValue": "1"},
        {"id": "c", "name": "empty", "kind": "env", "envName": "", "envValue": "1"},
    ]
    assert [v["id"] for v in coerce_custom_vars(raw)] == ["a"]


def test_arg_requires_flag():
    raw = [
        {"id": "a", "name": "ok", "kind": "arg", "arg": "-good"},
        {"id": "b", "name": "empty", "kind": "arg", "arg": ""},
        {"id": "c", "name": "missing", "kind": "arg"},
    ]
    assert [v["id"] for v in coerce_custom_vars(raw)] == ["a"]


def test_strips_unknown_fields():
    raw = [{"id": "a", "name": "FPS", "kind": "env", "envName": "X", "envValue": "1", "evil": "hax"}]
    assert coerce_custom_vars(raw) == [
        {"id": "a", "name": "FPS", "kind": "env", "envName": "X", "envValue": "1"},
    ]


def test_env_value_defaults_to_empty_when_absent():
    raw = [{"id": "a", "name": "bare", "kind": "env", "envName": "X"}]
    assert coerce_custom_vars(raw) == [
        {"id": "a", "name": "bare", "kind": "env", "envName": "X", "envValue": ""},
    ]


def test_dedupes_by_id_keeping_first():
    raw = [
        {"id": "a", "name": "first", "kind": "arg", "arg": "-1"},
        {"id": "a", "name": "second", "kind": "arg", "arg": "-2"},
    ]
    assert [v["name"] for v in coerce_custom_vars(raw)] == ["first"]
