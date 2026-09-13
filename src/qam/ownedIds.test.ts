import { describe, expect, it } from "vitest";

import { PDC_QAM_TAB_ID } from "../deckyInternal";
import { assignOwnedIds } from "./ownedIds";

describe("QAM owned ID allocation", () => {
  it("keeps Inicio on the legacy ID and assigns stable adjacent IDs", () => {
    expect(assignOwnedIds(
      ["pdc:home", "pdc:section:hud"],
      {},
      new Set([999]),
    )).toEqual({
      "pdc:home": PDC_QAM_TAB_ID,
      "pdc:section:hud": PDC_QAM_TAB_ID + 1,
    });
  });

  it("preserves inactive assignments and reuses existing IDs", () => {
    const existing = {
      "pdc:view:retired": PDC_QAM_TAB_ID + 1,
      "pdc:section:hud": PDC_QAM_TAB_ID + 7,
    };

    expect(assignOwnedIds(["pdc:section:hud", "pdc:section:power"], existing, new Set([999])))
      .toEqual({
        "pdc:view:retired": PDC_QAM_TAB_ID + 1,
        "pdc:section:hud": PDC_QAM_TAB_ID + 7,
        "pdc:section:power": PDC_QAM_TAB_ID + 2,
      });
  });

  it("skips IDs occupied by another QAM owner", () => {
    expect(assignOwnedIds(
      ["pdc:section:hud"],
      {},
      new Set([PDC_QAM_TAB_ID + 1]),
    )).toEqual({ "pdc:section:hud": PDC_QAM_TAB_ID + 2 });
  });

  it("rejects a collision with the fixed Inicio ID", () => {
    expect(() => assignOwnedIds(
      ["pdc:home"],
      {},
      new Set([PDC_QAM_TAB_ID]),
    )).toThrow("home_id_occupied");
  });

  it("rejects duplicate persisted assignments", () => {
    expect(() => assignOwnedIds(
      ["pdc:section:hud"],
      {
        "pdc:section:hud": PDC_QAM_TAB_ID + 1,
        "pdc:section:power": PDC_QAM_TAB_ID + 1,
      },
      new Set(),
    )).toThrow("owned_id_duplicate");
  });
});
