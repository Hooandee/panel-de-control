extends VBoxContainer

const ObservedValue = preload(
	"res://plugins/panel-de-control/core/domain/observed_value.gd"
)
const PowerStationAdapter = preload(
	"res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd"
)

@onready var _powerstation_status: Label = %PowerStationStatus
@onready var _gpu_value: Label = %GpuValue
@onready var _tdp_value: Label = %TdpValue
@onready var _power_profile_value: Label = %PowerProfileValue
@onready var _refresh_timer: Timer = $RefreshTimer

var _adapter: RefCounted
var _shutting_down := false


func configure_source(source: Variant) -> void:
	_adapter = PowerStationAdapter.new(source)


func _ready() -> void:
	if _adapter == null:
		_adapter = PowerStationAdapter.new(null)
	_refresh_timer.timeout.connect(refresh_now)
	refresh_now()
	_refresh_timer.start()


func refresh_now() -> void:
	if _shutting_down or _adapter == null:
		return
	var snapshot: RefCounted = _adapter.read_snapshot()
	_powerstation_status.text = "PowerStation: %s" % _format_status(snapshot.gpu_identity)
	_gpu_value.text = "GPU: %s" % _format_gpu(snapshot.gpu_identity)
	_tdp_value.text = "Observed TDP: %s" % _format_tdp(snapshot.tdp_w)
	_power_profile_value.text = "Power profile: %s" % _format_observation(
		snapshot.power_profile
	)


func shutdown() -> void:
	_shutting_down = true
	if is_instance_valid(_refresh_timer):
		_refresh_timer.stop()
		if _refresh_timer.timeout.is_connected(refresh_now):
			_refresh_timer.timeout.disconnect(refresh_now)
	_adapter = null


func _format_status(observed: RefCounted) -> String:
	if observed.state == ObservedValue.KNOWN:
		return "Connected"
	return _format_observation(observed)


func _format_gpu(observed: RefCounted) -> String:
	if observed.state != ObservedValue.KNOWN:
		return _format_observation(observed)
	var identity: Dictionary = observed.value
	var name := String(identity.get("name", ""))
	var device := String(identity.get("device", ""))
	if not name.is_empty() and not device.is_empty():
		return "%s (%s)" % [name, device]
	if not name.is_empty():
		return name
	if not device.is_empty():
		return device
	return String(identity.get("dbus_path", ""))


func _format_tdp(observed: RefCounted) -> String:
	if observed.state == ObservedValue.KNOWN:
		return "%.1f W" % float(observed.value)
	return _format_observation(observed)


func _format_observation(observed: RefCounted) -> String:
	if observed.state == ObservedValue.KNOWN:
		return str(observed.value)
	var state := String(observed.state).capitalize()
	if observed.reason.is_empty():
		return state
	return "%s (%s)" % [state, observed.reason]
