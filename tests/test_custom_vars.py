from launch.custom_vars import coerce_custom_vars


def test_valid_list_passes_through():
    raw = [
        {"id": "a", "name": "FPS", "kind": "env", "envName": "DXVK_FRAME_RATE", "envValue": "60"},
        {"id": "b", "name": "Custom joy", "kind": "arg", "arg": "-my-nojoy"},
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


def test_drops_values_that_cannot_be_serialized_safely():
    raw = [
        {"id": "a", "name": "space", "kind": "env", "envName": "FOO", "envValue": "hello world"},
        {"id": "b", "name": "shell", "kind": "env", "envName": "BAR", "envValue": "$(bad)"},
        {"id": "c", "name": "multi", "kind": "arg", "arg": "--foo bar"},
        {"id": "d", "name": "ok", "kind": "env", "envName": "GOOD", "envValue": "dxgi=n,b"},
    ]
    assert [v["id"] for v in coerce_custom_vars(raw)] == ["d"]


def test_dedupes_by_owned_token_keeping_first():
    raw = [
        {"id": "a", "name": "first", "kind": "arg", "arg": "-custom"},
        {"id": "b", "name": "second", "kind": "arg", "arg": "-custom"},
        {"id": "c", "name": "env first", "kind": "env", "envName": "FOO", "envValue": "1"},
        {"id": "d", "name": "env second", "kind": "env", "envName": "FOO", "envValue": "2"},
    ]
    assert [v["id"] for v in coerce_custom_vars(raw)] == ["a", "c"]


def test_drops_tokens_owned_by_the_base_catalog():
    raw = [
        {"id": "a", "name": "base env", "kind": "env", "envName": "PROTON_LOG", "envValue": "1"},
        {"id": "b", "name": "base arg", "kind": "arg", "arg": "-novid"},
        {"id": "c", "name": "custom", "kind": "arg", "arg": "-my-flag"},
    ]
    assert [v["id"] for v in coerce_custom_vars(raw)] == ["c"]


def test_preserves_only_a_boolean_retired_marker():
    raw = [
        {"id": "a", "name": "old", "kind": "arg", "arg": "-old", "retired": True},
        {"id": "b", "name": "live", "kind": "arg", "arg": "-live", "retired": "yes"},
    ]
    assert coerce_custom_vars(raw) == [
        {"id": "a", "name": "old", "kind": "arg", "arg": "-old", "retired": True},
        {"id": "b", "name": "live", "kind": "arg", "arg": "-live"},
    ]
