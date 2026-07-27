extends GutTest

const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")
const PowerStationAdapter = preload("res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd")
const FakePowerStation = preload("res://plugins/panel-de-control/tests/support/fake_powerstation.gd")

var _powerstation: Variant


func after_each() -> void:
	if _powerstation != null:
		assert_eq(_powerstation.write_attempts(), 0, "adapter must remain read-only")
	_powerstation = null


func test_service_absent_returns_fresh_unavailable_snapshot() -> void:
	var adapter = PowerStationAdapter.new(null, func() -> int: return 1000)

	var first = adapter.read_snapshot()
	var second = adapter.read_snapshot()

	assert_eq(first.generation, 1)
	assert_eq(second.generation, 2)
	assert_ne(first, second)
	assert_eq(first.timestamp_msec, 1000)
	assert_eq(first.ownership, "external_powerstation")
	_assert_observed(first.gpu_identity, ObservedValue.UNAVAILABLE, "powerstation_unavailable")
	_assert_observed(first.tdp_w, ObservedValue.UNAVAILABLE, "powerstation_unavailable")
	_assert_read_only_fields(first)


func test_gpu_absent_invalidates_powerstation_observations() -> void:
	_powerstation = FakePowerStation.new([], true, false)
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	_assert_observed(snapshot.gpu_identity, ObservedValue.UNAVAILABLE, "gpu_unavailable")
	_assert_observed(snapshot.tdp_w, ObservedValue.UNAVAILABLE, "gpu_unavailable")
	_assert_observed(snapshot.power_profile, ObservedValue.UNAVAILABLE, "gpu_unavailable")


func test_unique_integrated_gpu_exposes_verifiable_values() -> void:
	_powerstation = FakePowerStation.new([_card()])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	assert_eq(snapshot.gpu_identity.state, ObservedValue.KNOWN)
	assert_eq(snapshot.gpu_identity.value, {
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
	})
	_assert_known(snapshot.tdp_w, 18.0)
	_assert_known(snapshot.power_profile, "balanced")
	_assert_read_only_fields(snapshot)


func test_zero_tdp_from_wrapper_is_unknown_even_when_capability_is_false() -> void:
	_powerstation = FakePowerStation.new([_card({
		"supports_tdp": false,
		"tdp": 0.0,
	})])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	_assert_observed(snapshot.tdp_w, ObservedValue.UNKNOWN, "tdp_not_supported")


func test_wrapper_error_defaults_are_never_promoted_to_known_values() -> void:
	_powerstation = FakePowerStation.new([_card({
		"dbus_path": "",
		"name": "",
		"device": "",
		"supports_tdp": false,
		"tdp": 0.0,
		"power_profile": "",
	})])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	_assert_observed(snapshot.gpu_identity, ObservedValue.UNKNOWN, "gpu_identity_unavailable")
	_assert_observed(snapshot.tdp_w, ObservedValue.UNKNOWN, "tdp_not_supported")
	_assert_observed(snapshot.power_profile, ObservedValue.UNKNOWN, "power_profile_unavailable")


func test_integrated_gpu_is_selected_from_mixed_cards_without_order_assumptions() -> void:
	_powerstation = FakePowerStation.new([
		_card({
			"dbus_path": "/org/shadowblip/Performance/GPU/card2",
			"class": "discrete",
			"name": "Discrete GPU",
			"device": "1002:73df",
			"tdp": 120.0,
			"power_profile": "performance",
		}),
		_card(),
	])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	assert_eq(snapshot.gpu_identity.value["class"], "integrated")
	assert_eq(snapshot.gpu_identity.value["dbus_path"], "/org/shadowblip/Performance/GPU/card1")
	_assert_known(snapshot.tdp_w, 18.0)


func test_multiple_integrated_gpus_are_ambiguous() -> void:
	_powerstation = FakePowerStation.new([
		_card(),
		_card({"dbus_path": "/org/shadowblip/Performance/GPU/card3"}),
	])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	_assert_observed(snapshot.gpu_identity, ObservedValue.UNKNOWN, "integrated_gpu_ambiguous")
	_assert_observed(snapshot.tdp_w, ObservedValue.UNKNOWN, "integrated_gpu_ambiguous")
	_assert_observed(snapshot.power_profile, ObservedValue.UNKNOWN, "integrated_gpu_ambiguous")


func test_discrete_only_system_does_not_select_a_gpu() -> void:
	_powerstation = FakePowerStation.new([_card({
		"class": "discrete",
		"name": "Discrete GPU",
	})])
	var snapshot = PowerStationAdapter.new(_powerstation).read_snapshot()

	_assert_observed(snapshot.gpu_identity, ObservedValue.UNKNOWN, "integrated_gpu_not_found")
	_assert_observed(snapshot.tdp_w, ObservedValue.UNKNOWN, "integrated_gpu_not_found")


func test_failed_snapshot_does_not_leak_values_and_next_read_recovers() -> void:
	_powerstation = FakePowerStation.new([_card()])
	var adapter = PowerStationAdapter.new(_powerstation)

	var valid = adapter.read_snapshot()
	_powerstation.running = false
	var failed = adapter.read_snapshot()
	_powerstation.running = true
	var recovered = adapter.read_snapshot()

	_assert_known(valid.tdp_w, 18.0)
	_assert_observed(failed.tdp_w, ObservedValue.UNAVAILABLE, "powerstation_not_running")
	assert_null(failed.tdp_w.value)
	_assert_known(recovered.tdp_w, 18.0)
	assert_eq(recovered.generation, 3)
	assert_ne(valid, recovered)


func _card(overrides: Dictionary = {}) -> Dictionary:
	var data := {
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
		"supports_tdp": true,
		"tdp": 18.0,
		"power_profile": "balanced",
	}
	data.merge(overrides, true)
	return data


func _assert_known(observed: Variant, expected: Variant) -> void:
	assert_eq(observed.state, ObservedValue.KNOWN)
	assert_eq(observed.value, expected)
	assert_eq(observed.reason, "")


func _assert_observed(observed: Variant, state: String, reason: String) -> void:
	assert_eq(observed.state, state)
	assert_eq(observed.reason, reason)


func _assert_read_only_fields(snapshot: Variant) -> void:
	_assert_observed(snapshot.requested_tdp_w, ObservedValue.UNKNOWN, "external_ownership")
	_assert_observed(snapshot.target_tdp_w, ObservedValue.UNKNOWN, "external_ownership")
	_assert_observed(snapshot.applied_tdp_w, ObservedValue.UNKNOWN, "external_ownership")
	_assert_observed(snapshot.thermal, ObservedValue.UNKNOWN, "not_observed")
	_assert_observed(snapshot.tdp_limits, ObservedValue.UNAVAILABLE, "not_exposed_by_powerstation")
