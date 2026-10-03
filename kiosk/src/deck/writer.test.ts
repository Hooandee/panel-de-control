import { describe, expect, it } from "vitest";

import { createCoalescedWriter } from "./writer";

function clock() {
  let t = 0;
  return {
    now: () => t,
    wait: async (ms: number) => {
      t += ms;
    },
    advance: (ms: number) => {
      t += ms;
    },
  };
}

describe("coalesced writer", () => {
  it("writes the first value at once and only the newest of a burst afterwards", async () => {
    const c = clock();
    const sent: number[] = [];
    let release: () => void = () => {};
    const writer = createCoalescedWriter<number>(
      (v) => {
        sent.push(v);
        return new Promise<void>((resolve) => {
          release = resolve;
        });
      },
      50,
      undefined,
      c.now,
      c.wait,
    );
    writer.push(1);
    writer.push(2);
    writer.push(3);
    writer.push(4);
    expect(sent).toEqual([1]);
    release();
    await Promise.resolve();
    await Promise.resolve();
    release();
    await writer.flush();
    expect(sent).toEqual([1, 4]);
  });

  it("keeps the gap between writes", async () => {
    const c = clock();
    const at: number[] = [];
    const writer = createCoalescedWriter<number>(async () => {
      at.push(c.now());
    }, 120, undefined, c.now, c.wait);
    writer.push(1);
    await writer.flush();
    c.advance(10);
    writer.push(2);
    await writer.flush();
    expect(at).toEqual([0, 120]);
  });

  it("reports a failed write and keeps going", async () => {
    const errors: unknown[] = [];
    const sent: number[] = [];
    const writer = createCoalescedWriter<number>(async (v) => {
      sent.push(v);
      if (v === 1) throw new Error("nope");
    }, 0, (e) => errors.push(e));
    writer.push(1);
    await writer.flush();
    writer.push(2);
    await writer.flush();
    expect(sent).toEqual([1, 2]);
    expect(errors).toHaveLength(1);
  });
});
