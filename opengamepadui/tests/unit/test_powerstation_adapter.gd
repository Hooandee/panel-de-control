extends GutTest

const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")
const PowerStationAdapter = preload(
	"res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd"
)


func test_flat_properties_create_a_known_read_only_snapshot() -> void:
	var adapter := _new_adapter()
	if adapter == null:
		return

	var snapshot = adapter.snapshot_from_properties({
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
	}, {
		"tdp": 18.0,
		"power_profile": "balanced",
	})

	assert_eq(snapshot.generation, 1)
	assert_eq(snapshot.timestamp_msec, 1000)
	assert_eq(snapshot.ownership, "external_powerstation")
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


func test_flat_default_values_are_never_promoted_to_known() -> void:
	var adapter := _new_adapter()
	if adapter == null:
		return

	var snapshot = adapter.snapshot_from_properties({
		"dbus_path": "",
		"class": "integrated",
		"name": "",
		"device": "",
	}, {
		"tdp": 0.0,
		"power_profile": "",
	})

	_assert_observed(snapshot.gpu_identity, ObservedValue.UNKNOWN, "gpu_identity_unavailable")
	_assert_observed(snapshot.tdp_w, ObservedValue.UNKNOWN, "tdp_value_invalid")
	_assert_observed(
		snapshot.power_profile,
		ObservedValue.UNKNOWN,
		"power_profile_unavailable"
	)


func test_invalid_snapshot_uses_causal_unreachable_reason_without_stale_values() -> void:
	var adapter := _new_adapter()
	if adapter == null:
		return
	var valid = adapter.snapshot_from_properties({
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
	}, {
		"tdp": 18.0,
		"power_profile": "balanced",
	})

	var failed = adapter.invalid_snapshot(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable"
	)

	_assert_known(valid.tdp_w, 18.0)
	_assert_observed(
		failed.gpu_identity,
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable"
	)
	_assert_observed(
		failed.tdp_w,
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable"
	)
	assert_null(failed.tdp_w.value)
	assert_eq(failed.generation, 2)


func test_unknown_and_error_invalidations_preserve_their_state() -> void:
	var adapter := _new_adapter()
	if adapter == null:
		return

	var unknown = adapter.invalid_snapshot(
		ObservedValue.UNKNOWN,
		"integrated_gpu_not_found"
	)
	var failed = adapter.invalid_snapshot(ObservedValue.ERROR, "busctl_response_invalid")

	_assert_observed(
		unknown.gpu_identity,
		ObservedValue.UNKNOWN,
		"integrated_gpu_not_found"
	)
	_assert_observed(
		failed.gpu_identity,
		ObservedValue.ERROR,
		"busctl_response_invalid"
	)


func _new_adapter() -> RefCounted:
	var adapter := PowerStationAdapter.new(func() -> int: return 1000)
	assert_true(
		adapter.has_method("snapshot_from_properties"),
		"adapter must transform flat dictionaries instead of calling PowerStation Gd objects"
	)
	if not adapter.has_method("snapshot_from_properties"):
		return null
	return adapter


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
