extends RefCounted

const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")

const OWNERSHIP := "external_powerstation"

var generation: int
var timestamp_msec: int
var ownership := OWNERSHIP
var gpu_identity: Variant
var tdp_w: Variant
var power_profile: Variant
var requested_tdp_w: Variant
var target_tdp_w: Variant
var applied_tdp_w: Variant
var thermal: Variant
var tdp_limits: Variant


func _init(snapshot_generation: int, snapshot_timestamp_msec: int) -> void:
	generation = snapshot_generation
	timestamp_msec = snapshot_timestamp_msec
	gpu_identity = ObservedValue.unknown("not_observed")
	tdp_w = ObservedValue.unknown("not_observed")
	power_profile = ObservedValue.unknown("not_observed")
	requested_tdp_w = ObservedValue.unknown("external_ownership")
	target_tdp_w = ObservedValue.unknown("external_ownership")
	applied_tdp_w = ObservedValue.unknown("external_ownership")
	thermal = ObservedValue.unknown("not_observed")
	tdp_limits = ObservedValue.unavailable("not_exposed_by_powerstation")
