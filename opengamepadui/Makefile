PLUGIN_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PLUGIN_ID := panel-de-control
PLUGIN_NAME := Panel de Control

OGUI_DIR ?= $(abspath $(PLUGIN_DIR)/../OpenGamepadUI)
GODOT ?= godot
PYTHON ?= python3
HOST ?=
SSH_USER ?= deck
DIST_DIR ?= $(PLUGIN_DIR)/dist
PACKAGE := $(DIST_DIR)/$(PLUGIN_ID).zip
OGUI_PLUGIN := $(OGUI_DIR)/plugins/$(PLUGIN_ID)
GUT_SCRIPT := res://addons/gut/gut_cmdln.gd
SMOKE_SCRIPT := $(PLUGIN_DIR)/tests/package_smoke.gd

.PHONY: link test dist validate smoke install configure

link:
	@test -f "$(OGUI_DIR)/project.godot" || { echo "OpenGamepadUI checkout not found: $(OGUI_DIR)" >&2; exit 1; }
	@mkdir -p "$(OGUI_DIR)/plugins"
	@if test -L "$(OGUI_PLUGIN)"; then \
		test "$$(cd "$$(dirname "$$(readlink "$(OGUI_PLUGIN)")")" && pwd)/$$(basename "$$(readlink "$(OGUI_PLUGIN)")")" = "$(PLUGIN_DIR)" || { echo "Plugin link points elsewhere: $(OGUI_PLUGIN)" >&2; exit 1; }; \
	elif test -e "$(OGUI_PLUGIN)"; then \
		echo "Plugin path already exists and is not a symlink: $(OGUI_PLUGIN)" >&2; exit 1; \
	else \
		ln -s "$(PLUGIN_DIR)" "$(OGUI_PLUGIN)"; \
	fi

configure:
	$(PYTHON) "$(PLUGIN_DIR)/scripts/configure_export.py" \
		--ogui-dir "$(OGUI_DIR)" \
		--template "$(PLUGIN_DIR)/export_presets.cfg"

test: link
	$(GODOT) --headless --path "$(OGUI_DIR)" --import
	$(GODOT) --headless --path "$(OGUI_DIR)" --script "$(GUT_SCRIPT)" \
		-gdir=res://plugins/$(PLUGIN_ID)/tests/unit \
		-ginclude_subdirs \
		-gexit

dist: link configure
	@mkdir -p "$(DIST_DIR)"
	$(GODOT) --headless --path "$(OGUI_DIR)" --import
	$(GODOT) --headless --path "$(OGUI_DIR)" \
		--export-pack "$(PLUGIN_NAME)" "$(PACKAGE)"
	$(PYTHON) "$(PLUGIN_DIR)/scripts/validate_package.py" \
		--package "$(PACKAGE)" \
		--source "$(PLUGIN_DIR)"

validate:
	$(PYTHON) "$(PLUGIN_DIR)/scripts/validate_package.py" \
		--package "$(PACKAGE)" \
		--source "$(PLUGIN_DIR)"

smoke: link validate
	@set -eu; \
	link_target=$$(readlink "$(OGUI_PLUGIN)"); \
	restore_link() { \
		if ! test -e "$(OGUI_PLUGIN)" && ! test -L "$(OGUI_PLUGIN)"; then \
			ln -s "$$link_target" "$(OGUI_PLUGIN)"; \
		fi; \
	}; \
	trap restore_link EXIT; \
	unlink "$(OGUI_PLUGIN)"; \
	$(GODOT) --headless --path "$(OGUI_DIR)" \
		--script "$(SMOKE_SCRIPT)" -- "$(PACKAGE)"

install: dist
	bash "$(PLUGIN_DIR)/scripts/install_to_device.sh" \
		--host "$(HOST)" \
		--user "$(SSH_USER)" \
		--package "$(PACKAGE)"
