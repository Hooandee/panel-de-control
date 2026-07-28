extends SceneTree

const PLUGIN_ENTRYPOINT := "res://plugins/panel-de-control/plugin.gd"
const PLUGIN_SCENE := (
	"res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
)


func _init() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 1:
		_fail("Expected exactly one plugin package path")
		return
	if FileAccess.file_exists(PLUGIN_ENTRYPOINT):
		_fail("Plugin source is visible before mounting the package")
		return
	if not ProjectSettings.load_resource_pack(arguments[0]):
		_fail("Unable to mount plugin resource pack")
		return

	var plugin_script := load(PLUGIN_ENTRYPOINT) as GDScript
	if plugin_script == null:
		_fail("Unable to load compiled plugin entrypoint")
		return
	var plugin_instance := plugin_script.new() as Node
	if plugin_instance == null:
		_fail("Unable to instantiate compiled plugin entrypoint")
		return

	var menu_scene := load(PLUGIN_SCENE) as PackedScene
	if menu_scene == null:
		plugin_instance.free()
		_fail("Unable to load compiled plugin scene")
		return
	var menu_instance := menu_scene.instantiate()
	if menu_instance == null:
		plugin_instance.free()
		_fail("Unable to instantiate compiled plugin scene")
		return

	menu_instance.free()
	plugin_instance.free()
	print("Plugin package smoke test passed")
	quit(0)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
