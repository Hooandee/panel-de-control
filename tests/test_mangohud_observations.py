from mangohud.observations import TimedValue, fresh_value


def test_fresh_value_requires_recent_confirmed_observation():
    assert fresh_value(TimedValue(15, 10.0, True), 13.0, 3.0) == 15
    assert fresh_value(TimedValue(15, 10.0, True), 13.1, 3.0) is None
    assert fresh_value(TimedValue(15, 10.0, False), 10.1, 3.0) is None
    assert fresh_value(None, 10.1, 3.0) is None
