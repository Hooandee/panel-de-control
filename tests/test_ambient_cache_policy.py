from ambient.core.cache_policy import cache_filename, is_expired


def test_filename_is_stable_and_typed():
    a = cache_filename("https://x.test/a?b=1", "image/jpeg")
    assert a == cache_filename("https://x.test/a?b=1", "image/jpeg")
    assert a.endswith(".jpg")
    assert len(a.split(".")[0]) == 64


def test_filename_rejects_unknown_mime():
    assert cache_filename("https://x.test/a", "text/html") is None


def test_daily_sources_expire_after_a_day():
    assert not is_expired(fetched_at=1000, now=1000 + 3600, daily=True)
    assert is_expired(fetched_at=1000, now=1000 + 90000, daily=True)
    assert not is_expired(fetched_at=1000, now=1000 + 10**8, daily=False)
