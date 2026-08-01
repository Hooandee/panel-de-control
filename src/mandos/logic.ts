import type { ControllerButtonAction, ControllerTarget } from "../api";

const MANAGER_LABEL: Record<string, string> = {
  hhd: "mandos.manager.hhd",
  inputplumber: "mandos.manager.ip",
  none: "mandos.manager.none",
};

/** i18n key for the friendly name of the controller manager. */
export function managerLabelKey(manager: string): string {
  return MANAGER_LABEL[manager] ?? MANAGER_LABEL.none;
}

/** i18n key for the plain-language explanation of what this manager does. */
export function managerDescKey(manager: string): string {
  return `mandos.desc.${manager in MANAGER_LABEL ? manager : "none"}`;
}

// ── Remap target encoding ───────────────────────────────────────────────────
// A remap target is a gamepad button or a keyboard key. We flatten it to a single
// string so it fits a Dropdown's option `data`, and parse it back on change.

export function targetToValue(t: ControllerTarget): string {
  return "gamepad" in t ? `gp:${t.gamepad}` : `key:${t.key}`;
}

export function valueToTarget(value: string): ControllerTarget {
  const i = value.indexOf(":");
  const kind = value.slice(0, i);
  const name = value.slice(i + 1);
  return kind === "key" ? { key: name } : { gamepad: name };
}

/** The dropdown value for a button's current mapping (its first target), or "". */
export function currentTargetValue(targets: ControllerTarget[]): string {
  return targets.length ? targetToValue(targets[0]) : "";
}

export function targetsToAction(targets: ControllerTarget[]): ControllerButtonAction {
  if (targets.length === 1 && "gamepad" in targets[0]) {
    return { kind: "gamepad", target: targets[0].gamepad };
  }
  if (targets.length > 0 && targets.every((target) => "key" in target)) {
    return {
      kind: "keyboard_chord",
      keys: targets.map((target) => (target as { key: string }).key),
    };
  }
  return { kind: "default" };
}

export function actionToTargets(action: ControllerButtonAction): ControllerTarget[] {
  if (action.kind === "gamepad") return [{ gamepad: action.target }];
  if (action.kind === "keyboard_chord") {
    return action.keys.map((key) => ({ key }));
  }
  return [];
}

const KEY_LABELS: Record<string, string> = {
  KeyLeftCtrl: "Ctrl", KeyRightCtrl: "Right Ctrl",
  KeyLeftShift: "Shift", KeyRightShift: "Right Shift",
  KeyLeftAlt: "Alt", KeyRightAlt: "Alt Gr",
  KeyLeftMeta: "Meta", KeyRightMeta: "Right Meta",
  KeyEsc: "Esc", KeyEnter: "Enter", KeySpace: "Space", KeyTab: "Tab",
  KeyBackspace: "Backspace", KeyPageUp: "Page Up", KeyPageDown: "Page Down",
  KeyVolumeUp: "Volume +", KeyVolumeDown: "Volume −", KeyMute: "Mute",
  KeyBrightnessUp: "Brightness +", KeyBrightnessDown: "Brightness −",
  KeyUp: "↑", KeyDown: "↓", KeyLeft: "←", KeyRight: "→",
};

export function prettyKey(key: string): string {
  return KEY_LABELS[key] ?? key.replace(/^Key/, "");
}

export function prettyAction(action: ControllerButtonAction): string {
  if (action.kind === "gamepad") return prettyTarget(`gp:${action.target}`);
  if (action.kind === "keyboard_chord") {
    return action.keys.map(prettyKey).join(" + ");
  }
  return "";
}

// Friendly labels: Xbox face-button letters + short paddle/shoulder names. Anything
// unmapped falls through to the raw name (don't invent a label we don't know).
const GP_LABEL: Record<string, string> = {
  South: "A", East: "B", West: "X", North: "Y",
  LeftBumper: "LB", RightBumper: "RB", LeftTrigger: "LT", RightTrigger: "RT",
  LeftStick: "L3", RightStick: "R3",
};

export function prettyTarget(value: string): string {
  const t = valueToTarget(value);
  if ("key" in t) return prettyKey(t.key);
  return GP_LABEL[t.gamepad] ?? t.gamepad;
}
