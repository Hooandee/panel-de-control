from controllers import conflict


def test_managing_power_true_when_hhd_tdp_enabled():
    state = {"hhd": {"settings": {"tdp_enable": True}}}
    assert conflict.hhd_managing_power(state) is True


def test_managing_power_false_when_disabled():
    state = {"hhd": {"settings": {"tdp_enable": False}}}
    assert conflict.hhd_managing_power(state) is False


def test_managing_power_false_when_no_state():
    assert conflict.hhd_managing_power(None) is False
    assert conflict.hhd_managing_power({}) is False


def test_conflict_needs_both_sides():
    state = {"hhd": {"settings": {"tdp_enable": True}}}
    # HHD manages power AND we can drive power on this device → real conflict.
    assert conflict.assess(state, our_tdp_supported=True)["conflict"] is True
    # We can't drive power (NullBackend) → no fight even if HHD is on.
    assert conflict.assess(state, our_tdp_supported=False)["conflict"] is False
    # HHD off → no fight.
    off = {"hhd": {"settings": {"tdp_enable": False}}}
    assert conflict.assess(off, our_tdp_supported=True)["conflict"] is False


def test_assess_reports_managing_flag():
    state = {"hhd": {"settings": {"tdp_enable": True}}}
    out = conflict.assess(state, our_tdp_supported=False)
    assert out["hhd_managing_power"] is True
    assert out["conflict"] is False
