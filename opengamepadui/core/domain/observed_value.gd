extends RefCounted

const KNOWN := "known"
const UNAVAILABLE := "unavailable"
const UNKNOWN := "unknown"
const ERROR := "error"

var state: String
var value: Variant
var reason: String


func _init(observation_state: String, observation_value: Variant, observation_reason: String) -> void:
	state = observation_state
	value = observation_value
	reason = observation_reason


static func known(observation_value: Variant) -> RefCounted:
	return new(KNOWN, observation_value, "")


static func unavailable(observation_reason: String) -> RefCounted:
	return new(UNAVAILABLE, null, observation_reason)


static func unknown(observation_reason: String) -> RefCounted:
	return new(UNKNOWN, null, observation_reason)


static func error(observation_reason: String) -> RefCounted:
	return new(ERROR, null, observation_reason)
