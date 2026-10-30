import type { OverlayCorner } from "./types";

/** Steam's gamepad button codes as they reach a focused node (EGamepadButton). */
export const GamepadButton = {
  A: 1,
  B: 2,
  X: 3,
  Y: 4,
  L1: 5,
  R1: 6,
  L2: 7,
  R2: 8,
  UP: 9,
  DOWN: 10,
  LEFT: 11,
  RIGHT: 12,
  R3: 16,
  STEAM: 27,
  QUICK_ACCESS: 28,
} as const;

export type ControlAction =
  | { kind: "toggle" }
  | { kind: "next" }
  | { kind: "video" }
  | { kind: "fullscreen" }
  | { kind: "move"; corner: OverlayCorner }
  | { kind: "seek"; seconds: number }
  | { kind: "resize"; direction: -1 | 1 }
  | { kind: "exit"; then?: "main-menu" | "quick-access" }
  | { kind: "ignore" };

export const CONTROL_IDLE_MS = 10000;

/** Every button the card answers to; Steam and QAM are left to Steam. */
export const CONTROL_BUTTONS: readonly number[] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16];

function moved(corner: OverlayCorner, button: number): OverlayCorner {
  const [vertical, horizontal] = corner.split("-") as ["top" | "bottom", "left" | "right"];
  if (button === GamepadButton.UP) return `top-${horizontal}`;
  if (button === GamepadButton.DOWN) return `bottom-${horizontal}`;
  if (button === GamepadButton.LEFT) return `${vertical}-left`;
  return `${vertical}-right`;
}

export function controlAction(button: number, corner: OverlayCorner): ControlAction {
  switch (button) {
    case GamepadButton.A:
      return { kind: "toggle" };
    case GamepadButton.X:
      return { kind: "next" };
    case GamepadButton.R3:
      return { kind: "fullscreen" };
    case GamepadButton.Y:
      return { kind: "video" };
    case GamepadButton.UP:
    case GamepadButton.DOWN:
    case GamepadButton.LEFT:
    case GamepadButton.RIGHT:
      return { kind: "move", corner: moved(corner, button) };
    case GamepadButton.L1:
      return { kind: "seek", seconds: -10 };
    case GamepadButton.R1:
      return { kind: "seek", seconds: 10 };
    case GamepadButton.L2:
      return { kind: "resize", direction: -1 };
    case GamepadButton.R2:
      return { kind: "resize", direction: 1 };
    case GamepadButton.B:
      return { kind: "exit" };
    case GamepadButton.STEAM:
      return { kind: "exit", then: "main-menu" };
    case GamepadButton.QUICK_ACCESS:
      return { kind: "exit", then: "quick-access" };
    default:
      return { kind: "ignore" };
  }
}

const KEYS: Record<string, number> = {
  Enter: GamepadButton.A,
  " ": GamepadButton.A,
  f: GamepadButton.R3,
  F: GamepadButton.R3,
  n: GamepadButton.X,
  N: GamepadButton.X,
  v: GamepadButton.Y,
  V: GamepadButton.Y,
  ArrowUp: GamepadButton.UP,
  ArrowDown: GamepadButton.DOWN,
  ArrowLeft: GamepadButton.LEFT,
  ArrowRight: GamepadButton.RIGHT,
  Escape: GamepadButton.B,
  "[": GamepadButton.L1,
  "]": GamepadButton.R1,
  "-": GamepadButton.L2,
  "+": GamepadButton.R2,
  Backspace: GamepadButton.B,
};

/** Keyboards drive the card like a controller; unknown keys map to nothing. */
export function keyToButton(key: string): number | null {
  return KEYS[key] ?? null;
}
