from gpu.profiles import GpuProfileStore


def test_gpu_profiles_keep_global_and_game_scopes_independent(tmp_path):
    store = GpuProfileStore(str(tmp_path / "gpu_profiles.json"))
    store.set_clock("global", True, 800, 2_000)

    assert store.clock("42") == {"manual": True, "min": 800, "max": 2_000}
    assert store.is_following_global("42") is True

    store.set_clock("game", True, 1_200, 2_400, appid="42")
    assert store.clock("42") == {"manual": True, "min": 1_200, "max": 2_400}
    assert store.is_following_global("42") is False

    store.set_follow_global("42", True)
    assert store.clock("42") == {"manual": True, "min": 800, "max": 2_000}
    assert store.game_profile("42") == {"manual": True, "min": 1_200, "max": 2_400}


def test_gpu_profiles_sanitize_malformed_values(tmp_path):
    path = tmp_path / "gpu_profiles.json"
    path.write_text('{"global":{"manual":true,"min":"bad","max":2400}}')

    store = GpuProfileStore(str(path))

    assert store.clock(None) == {"manual": False, "min": None, "max": None}
