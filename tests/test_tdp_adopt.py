from tdp.adopt import should_adopt_external

THRESH = 2


def test_no_data():
    assert should_adopt_external(None, 13, None, THRESH) == (False, None)
    assert should_adopt_external(30, None, None, THRESH) == (False, None)


def test_within_threshold_never_adopts_and_clears_pending():
    # A 1 W wobble is not an external change; any armed candidate is dropped.
    assert should_adopt_external(14, 13, 30, THRESH) == (False, None)


def test_first_divergence_arms_but_does_not_adopt():
    # A one-shot spike must NOT be adopted on its first sighting.
    assert should_adopt_external(30, 13, None, THRESH) == (False, 30)


def test_same_divergence_twice_adopts():
    # Persisted across two reads → a real external change; adopt and clear.
    assert should_adopt_external(30, 13, 30, THRESH) == (True, None)


def test_moving_target_re_arms_without_adopting():
    # Value diverges but differs from the armed candidate → re-arm, don't adopt.
    assert should_adopt_external(30, 13, 28, THRESH) == (False, 30)


def test_transient_then_back_in_range_is_dropped():
    # Spike sighted (armed 30), next read is back at the setpoint → cleared, no adopt.
    assert should_adopt_external(13, 13, 30, THRESH) == (False, None)
