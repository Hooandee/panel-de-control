import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));
vi.mock("@decky/ui", () => ({ PanelSectionRow: () => null, ToggleField: () => null }));

import type { BoardFanState } from "../api";
import { boardFanNote, boardFanToggleVisible } from "./BoardFanCard";

describe("boardFanNote", () => {
  it.each([
    [{ supported: true, available: [], channels: 0 }, "fans.board.noDriver"],
    [{ supported: true, available: ["nct6775"], channels: 0 }, "fans.board.note"],
    [{ supported: true, available: ["nct6775"], channels: 0,
       last: { action: "load", ok: false, channels: 0, detail: "no_board_fans" } }, "fans.board.noFans"],
    [{ supported: true, available: ["nct6775"], channels: 3, enabled: true }, "fans.board.active"],
    [{ supported: true, available: [], channels: 2, enabled: false }, "fans.board.present"],
  ] as [BoardFanState, string][])("picks an honest note for %j", (state, key) => {
    expect(boardFanNote(state)).toBe(key);
  });
});

describe("boardFanToggleVisible", () => {
  it("keeps the toggle reachable after opting out of fans no listed driver provides", () => {
    expect(boardFanToggleVisible({ supported: true, available: [], channels: 0, control_off: true })).toBe(true);
    expect(boardFanToggleVisible({ supported: true, available: [], channels: 2 })).toBe(true);
    expect(boardFanToggleVisible({ supported: true, available: [], channels: 0 })).toBe(false);
  });
});
