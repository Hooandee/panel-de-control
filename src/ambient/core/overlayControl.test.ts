import { describe, expect, it } from "vitest";

import { GamepadButton, controlAction, keyToButton } from "./overlayControl";

describe("controlAction", () => {
  it("drives playback with face buttons", () => {
    expect(controlAction(GamepadButton.A, "top-right")).toEqual({ kind: "toggle" });
    expect(controlAction(GamepadButton.X, "top-right")).toEqual({ kind: "next" });
    expect(controlAction(GamepadButton.Y, "top-right")).toEqual({ kind: "video" });
  });

  it("moves between corners with the d-pad", () => {
    expect(controlAction(GamepadButton.DOWN, "top-right")).toEqual({ kind: "move", corner: "bottom-right" });
    expect(controlAction(GamepadButton.LEFT, "bottom-right")).toEqual({ kind: "move", corner: "bottom-left" });
    expect(controlAction(GamepadButton.UP, "bottom-left")).toEqual({ kind: "move", corner: "top-left" });
    expect(controlAction(GamepadButton.RIGHT, "top-left")).toEqual({ kind: "move", corner: "top-right" });
  });

  it("hands Steam and QAM back to Steam after leaving", () => {
    expect(controlAction(GamepadButton.B, "top-left")).toEqual({ kind: "exit" });
    expect(controlAction(GamepadButton.STEAM, "top-left")).toEqual({ kind: "exit", then: "main-menu" });
    expect(controlAction(GamepadButton.QUICK_ACCESS, "top-left")).toEqual({ kind: "exit", then: "quick-access" });
    expect(controlAction(13, "top-left")).toEqual({ kind: "ignore" });
  });
});

describe("keyToButton", () => {
  it("maps a keyboard onto the controller layout", () => {
    expect(keyToButton("Enter")).toBe(GamepadButton.A);
    expect(keyToButton("n")).toBe(GamepadButton.X);
    expect(keyToButton("V")).toBe(GamepadButton.Y);
    expect(keyToButton("ArrowLeft")).toBe(GamepadButton.LEFT);
    expect(keyToButton("Escape")).toBe(GamepadButton.B);
    expect(keyToButton("q")).toBeNull();
  });
});

describe("seek and size", () => {
  it("uses the shoulders to skip and the triggers to resize", () => {
    expect(controlAction(GamepadButton.L1, "top-left")).toEqual({ kind: "seek", seconds: -10 });
    expect(controlAction(GamepadButton.R1, "top-left")).toEqual({ kind: "seek", seconds: 10 });
    expect(controlAction(GamepadButton.L2, "top-left")).toEqual({ kind: "resize", direction: -1 });
    expect(controlAction(GamepadButton.R2, "top-left")).toEqual({ kind: "resize", direction: 1 });
  });
});

it("opens fullscreen from the right stick or F without changing the video toggle", () => {
  expect(controlAction(GamepadButton.R3, "top-right")).toEqual({ kind: "fullscreen" });
  expect(keyToButton("f")).toBe(GamepadButton.R3);
  expect(keyToButton("F")).toBe(GamepadButton.R3);
});
