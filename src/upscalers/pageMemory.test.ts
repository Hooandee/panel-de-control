import { afterEach, describe, expect, it, vi } from "vitest";

import { holdPage, onDraft, releasePage, showGame, takeHeldPage, writeDraft } from "./pageMemory";

afterEach(() => {
  releasePage();
  vi.useRealTimers();
});

describe("game page across Steam's QAM remount", () => {
  it("hands back the open game and its unapplied choice after a menu", () => {
    showGame(292030);
    writeDraft(292030, { mode: "custom", choice: { build: "xess-2" } });
    holdPage();
    expect(takeHeldPage()).toEqual({ appid: 292030, draft: { mode: "custom", choice: { build: "xess-2" } } });
  });

  it("hands it back to a second mount too, as Decky 3.2.9 mounts the panel twice after a menu", () => {
    showGame(292030);
    holdPage();
    expect(takeHeldPage()?.appid).toBe(292030);
    expect(takeHeldPage()?.appid).toBe(292030);
  });

  it("drops the hold when another game opens", () => {
    showGame(292030);
    holdPage();
    showGame(1091500);
    expect(takeHeldPage()).toBeNull();
  });

  it("keeps nothing when the player closed the QAM without a menu or dialog", () => {
    showGame(292030);
    expect(takeHeldPage()).toBeNull();
  });

  it("forgets the page after leaving it", () => {
    showGame(292030);
    holdPage();
    showGame(null);
    expect(takeHeldPage()).toBeNull();
  });

  it("drops a hold the QAM never came back for", () => {
    vi.useFakeTimers();
    showGame(292030);
    holdPage();
    vi.advanceTimersByTime(3 * 60_000);
    expect(takeHeldPage()).toBeNull();
  });

  it("lets the remounted page hear a choice picked from the menu after it came back", () => {
    showGame(292030);
    const heard = vi.fn();
    const stop = onDraft(292030, heard);
    writeDraft(292030, { mode: "easy", choice: { fg: "on", fg_route: "game" } });
    writeDraft(1, { mode: "easy", choice: {} });
    stop();
    writeDraft(292030, { mode: "easy", choice: {} });
    expect(heard).toHaveBeenCalledTimes(1);
    expect(heard).toHaveBeenCalledWith({ mode: "easy", choice: { fg: "on", fg_route: "game" } });
  });
});
