import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ callable: () => vi.fn() }));

import { createPowerPort } from "./power";

const base = { present: true, percent: 42, status: "Discharging", ac_online: false };

async function first(read: () => Promise<unknown>) {
  const port = createPowerPort(read as never);
  return new Promise((resolve) => {
    const stop = port.subscribe((snapshot) => {
      stop();
      resolve(snapshot);
    });
  });
}

describe("power port", () => {
  afterEach(() => vi.useRealTimers());

  it("reports discharging battery", async () => {
    expect(await first(async () => ({ battery: base }))).toEqual({ battery: { percent: 42, charging: false } });
  });

  it("treats AC online as charging", async () => {
    expect(await first(async () => ({ battery: { ...base, ac_online: true } }))).toEqual({ battery: { percent: 42, charging: true } });
  });

  it("no battery or failed read is null", async () => {
    expect(await first(async () => ({ battery: { ...base, present: false } }))).toEqual({ battery: null });
    expect(await first(async () => { throw new Error("rpc"); })).toEqual({ battery: null });
  });
});
