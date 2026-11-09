import { expect, it, vi } from "vitest";
import { transitionFrameGen } from "./frameGenTransition";
it("restores completed changes in reverse order if a later provider fails", async () => {
  const order: string[] = [];
  await expect(transitionFrameGen([
    { apply: async () => { order.push("enable"); }, restore: async () => { order.push("undo enable"); } },
    { apply: async () => { order.push("retire"); }, restore: async () => { order.push("undo retire"); } },
    { apply: async () => { throw new Error("provider"); }, restore: vi.fn() },
  ])).rejects.toThrow("provider");
  expect(order).toEqual(["enable", "retire", "undo retire", "undo enable"]);
});
it("attempts every restoration and reports incomplete recovery", async () => {
  const restore = vi.fn().mockResolvedValue(undefined);
  await expect(transitionFrameGen([
    { apply: async () => {}, restore },
    { apply: async () => {}, restore: async () => { throw new Error("disk"); } },
    { apply: async () => { throw new Error("provider"); }, restore: vi.fn() },
  ])).rejects.toThrow("fg_restore_failed");
  expect(restore).toHaveBeenCalledOnce();
});
