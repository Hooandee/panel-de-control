import { describe, expect, it, vi } from "vitest";

import {
  claimQamSurface,
  getActiveQamSurface,
  subscribeActiveQamSurface,
} from "./qamSurfaceLease";

describe("QAM surface lease", () => {
  it("keeps the newest claimant active when an older surface releases late", () => {
    const standard = Symbol("standard");
    const hud = Symbol("hud");
    const releaseStandard = claimQamSurface("pdc:standard", standard);
    const releaseHud = claimQamSurface("pdc:section:hud", hud);

    releaseStandard();

    expect(getActiveQamSurface()).toBe(hud);
    releaseHud();
    expect(getActiveQamSurface()).toBeNull();
  });

  it("notifies only when the active surface actually changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeActiveQamSurface(listener);
    const releaseFirst = claimQamSurface("pdc:home", Symbol("first"));
    const releaseDuplicate = claimQamSurface("pdc:home", Symbol("duplicate"));

    releaseDuplicate();
    releaseFirst();

    expect(listener).toHaveBeenCalledTimes(4);
    unsubscribe();
  });
});
