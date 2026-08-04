import { describe, expect, it } from "vitest";
import * as controllerLogic from "./logic";

import {
  actionToTargets,
  currentTargetValue,
  managerDescKey,
  managerLabelKey,
  prettyTarget,
  targetToValue,
  targetsToAction,
  valueToTarget,
  vibrationNoteKey,
  isExperimentalHdVibration,
} from "./logic";

describe("managerLabelKey / managerDescKey", () => {
  it("maps known managers", () => {
    expect(managerLabelKey("hhd")).toBe("mandos.manager.hhd");
    expect(managerLabelKey("inputplumber")).toBe("mandos.manager.ip");
    expect(managerDescKey("inputplumber")).toBe("mandos.desc.inputplumber");
  });
  it("falls back to none for anything unknown", () => {
    expect(managerLabelKey("weird")).toBe("mandos.manager.none");
    expect(managerDescKey("weird")).toBe("mandos.desc.none");
  });
});

describe("target encoding", () => {
  it("round-trips gamepad + keyboard targets", () => {
    expect(targetToValue({ gamepad: "South" })).toBe("gp:South");
    expect(targetToValue({ key: "KeyEsc" })).toBe("key:KeyEsc");
    expect(valueToTarget("gp:South")).toEqual({ gamepad: "South" });
    expect(valueToTarget("key:KeyEsc")).toEqual({ key: "KeyEsc" });
  });
  it("currentTargetValue uses the first target, or empty", () => {
    expect(currentTargetValue([{ gamepad: "North" }, { gamepad: "West" }])).toBe("gp:North");
    expect(currentTargetValue([])).toBe("");
  });
  it("prettyTarget maps face buttons + strips Key prefix, else raw", () => {
    expect(prettyTarget("gp:South")).toBe("A");
    expect(prettyTarget("gp:LeftPaddle1")).toBe("LeftPaddle1");
    expect(prettyTarget("key:KeyEsc")).toBe("Esc");
  });
});

describe("controller button actions", () => {
  it("keeps a chord instead of only its first key", () => {
    expect(targetsToAction([
      { key: "KeyLeftCtrl" }, { key: "KeyTab" },
    ])).toEqual({
      kind: "keyboard_chord", keys: ["KeyLeftCtrl", "KeyTab"],
    });
  });

  it("round-trips default, gamepad and keyboard chord actions", () => {
    expect(actionToTargets({ kind: "default" })).toEqual([]);
    expect(actionToTargets({ kind: "gamepad", target: "South" }))
      .toEqual([{ gamepad: "South" }]);
    expect(actionToTargets({
      kind: "keyboard_chord", keys: ["KeyLeftAlt", "KeyEnter"],
    })).toEqual([{ key: "KeyLeftAlt" }, { key: "KeyEnter" }]);
  });
});

describe("vibrationNoteKey", () => {
  it("does not claim Lenovo readback when the driver only accepted writes", () => {
    expect(vibrationNoteKey({ mode: "lenovo_hd", confirmation: "none" }))
      .toBe("mandos.vibration.note.lenovoAccepted");
    expect(vibrationNoteKey({ mode: "lenovo_hd", confirmation: "driver" }))
      .toBe("mandos.vibration.note.lenovoHd");
  });

  it("explains the Xbox Ally X split ownership without claiming game transport", () => {
    expect(vibrationNoteKey({ mode: "asus_xbox_hd", confirmation: "driver" }))
      .toBe("mandos.vibration.note.xboxHd");
  });
});

describe("isExperimentalHdVibration", () => {
  it("marks the Legion Go 2 and Xbox Ally X native HD modes experimental", () => {
    expect(isExperimentalHdVibration("lenovo_hd")).toBe(true);
    expect(isExperimentalHdVibration("asus_xbox_hd")).toBe(true);
    expect(isExperimentalHdVibration("dual")).toBe(false);
    expect(isExperimentalHdVibration("gain")).toBe(false);
    expect(isExperimentalHdVibration(undefined)).toBe(false);
  });
});

describe("Xbox trigger test strength", () => {
  const vibrationTestStrength = (
    controllerLogic as unknown as {
      vibrationTestStrength?: (
        vibration: Record<string, unknown>, channel: string,
      ) => number | null;
    }
  ).vibrationTestStrength ?? (() => null);

  it.each([
    [0, "strong"],
    [70, "off"],
  ])("disables the test with gain %s and source %s", (gain, source) => {
    expect(vibrationTestStrength({
      mode: "asus_xbox_hd",
      hd_game_enabled: true,
      trigger_left: gain,
      trigger_left_source: source,
    }, "trigger_left")).toBe(0);
  });

  it("uses the configured strength when the trigger is enabled", () => {
    expect(vibrationTestStrength({
      mode: "asus_xbox_hd",
      hd_game_enabled: true,
      trigger_left: 35,
      trigger_left_source: "mix",
    }, "trigger_left")).toBe(35);
  });
});

describe("vibrationNotice", () => {
  const vibrationNotice = (
    controllerLogic as unknown as {
      vibrationNotice?: (
        vibration: { mode?: string; confirmation?: string; persistent?: boolean; last_apply?: boolean },
        testReason: string | null,
      ) => { key: string; tone: string } | null;
    }
  ).vibrationNotice ?? (() => null);

  it("prioritizes an apply failure over a test failure and the profile note", () => {
    expect(vibrationNotice({
      mode: "lenovo_hd",
      confirmation: "driver",
      persistent: true,
      last_apply: false,
    }, "stop_failed")).toEqual({
      key: "mandos.vibration.applyFailed",
      tone: "danger",
    });
  });

  it("shows one test failure instead of stacking the persistent note", () => {
    expect(vibrationNotice({
      mode: "lenovo_hd",
      confirmation: "driver",
      persistent: true,
    }, "restore_failed")).toEqual({
      key: "mandos.vibration.test.error.restore_failed",
      tone: "danger",
    });
  });

  it("uses the persistent profile note when there is no operational error", () => {
    expect(vibrationNotice({
      mode: "lenovo_hd",
      confirmation: "driver",
      persistent: true,
    }, null)).toEqual({
      key: "mandos.vibration.note.lenovoHd",
      tone: "muted",
    });
  });
});

describe("discrete vibration controls", () => {
  const choiceIndex = (
    controllerLogic as unknown as {
      choiceIndex?: (options: readonly string[], value: string) => number;
    }
  ).choiceIndex ?? (() => -1);
  const choiceAt = (
    controllerLogic as unknown as {
      choiceAt?: (options: readonly string[], index: number) => string | undefined;
    }
  ).choiceAt ?? (() => undefined);

  it("maps the live driver enums to slider indices and back", () => {
    const options = ["off", "low", "medium", "high"];
    expect(choiceIndex(options, "medium")).toBe(2);
    expect(choiceIndex(options, "unknown")).toBe(-1);
    expect(choiceAt(options, 3)).toBe("high");
    expect(choiceAt(options, 99)).toBe("high");
    expect(choiceAt([], 0)).toBeUndefined();
  });

});
