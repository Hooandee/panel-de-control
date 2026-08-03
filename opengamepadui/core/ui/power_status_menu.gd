extends VBoxContainer

const ObservedValue = preload(
	"res://plugins/panel-de-control/core/domain/observed_value.gd"
)

@onready var _powerstation_status: Label = %PowerStationStatus
@onready var _gpu_value: Label = %GpuValue
@onready var _tdp_value: Label = %TdpValue
@onready var _power_profile_value: Label = %PowerProfileValue
@onready var _refresh_timer: Timer = $RefreshTimer

var _sampler: Node
var _shutting_down := false


func configure_sampler(sampler: Node) -> void:
	_sampler = sampler


func _ready() -> void:
	if _sampler != null:
		_sampler.connect("snapshot_updated", _on_snapshot_updated)
		var latest_snapshot: RefCounted = _sampler.call("get_latest_snapshot")
		if latest_snapshot != null:
			_render_snapshot(latest_snapshot)
	_refresh_timer.timeout.connect(refresh_now)
	refresh_now()
	_refresh_timer.start()


func _process(_delta: float) -> void:
	if _shutting_down or _sampler == null:
		return
	_sampler.call("poll")


func refresh_now() -> void:
	if _shutting_down or _sampler == null:
		return
	_sampler.call("request_snapshot")


func _on_snapshot_updated(snapshot: RefCounted) -> void:
	if _shutting_down:
		return
	_render_snapshot(snapshot)


func _render_snapshot(snapshot: RefCounted) -> void:
	_powerstation_status.text = "PowerStation: %s" % _format_status(snapshot.gpu_identity)
	_gpu_value.text = "GPU: %s" % _format_gpu(snapshot.gpu_identity)
	_tdp_value.text = "Observed TDP: %s" % _format_tdp(snapshot.tdp_w)
	_power_profile_value.text = "Power profile: %s" % _format_observation(
		snapshot.power_profile
	)


func shutdown() -> void:
	_shutting_down = true
	set_process(false)
	if is_instance_valid(_refresh_timer):
		_refresh_timer.stop()
		if _refresh_timer.timeout.is_connected(refresh_now):
			_refresh_timer.timeout.disconnect(refresh_now)
	if (
		is_instance_valid(_sampler)
		and _sampler.is_connected("snapshot_updated", _on_snapshot_updated)
	):
		_sampler.disconnect("snapshot_updated", _on_snapshot_updated)
	_sampler = null


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
