import { describe, expect, it } from "vitest";

import { applyQamEntryTransaction } from "./transaction";

describe("QAM entry transaction", () => {
  it("applies an exact desired reference sequence", () => {
    const friends = { key: "friends" };
    const decky = { key: 999 };
    const hud = { key: 5_260_356 };
    const target = [friends, decky];

    expect(applyQamEntryTransaction(target, [hud, friends, decky], () => true))
      .toEqual({ applied: true });
    expect(target).toEqual([hud, friends, decky]);
  });

  it("restores the exact previous sequence when readback rejects the change", () => {
    const friends = { key: "friends" };
    const decky = { key: 999 };
    const target = [friends, decky];

    expect(applyQamEntryTransaction(target, [decky, friends], () => false))
      .toEqual({ applied: false, reason: "readback_mismatch" });
    expect(target).toEqual([friends, decky]);
    expect(target[0]).toBe(friends);
    expect(target[1]).toBe(decky);
  });

  it("restores after readback throws or mutates the materialization concurrently", () => {
    const friends = { key: "friends" };
    const decky = { key: 999 };
    const intruder = { key: "intruder" };
    const target = [friends, decky];

    const result = applyQamEntryTransaction(target, [decky, friends], () => {
      target.push(intruder);
      throw new Error("renderer changed");
    });

    expect(result).toEqual({ applied: false, reason: "readback_threw" });
    expect(target).toEqual([friends, decky]);
  });
});
