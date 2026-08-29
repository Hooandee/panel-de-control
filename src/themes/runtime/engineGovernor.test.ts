// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import { startEngineGovernor } from "./engineGovernor";

describe("theme engine governor", () => {
  it("suspends while hidden and enters efficient mode for performance or reduced motion", () => {
    const listeners = new Set<() => void>();
    const media = {
      matches: false,
      addEventListener: (_name: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_name: string, listener: () => void) => listeners.delete(listener),
    };
    const budgets: string[] = [];
    const stop = startEngineGovernor({
      doc: document,
      performance: false,
      motionIntensity: "full",
      media,
      onBudget: (budget) => budgets.push(budget),
    });

    expect(budgets).toEqual(["cinematic"]);
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(budgets[budgets.length - 1]).toBe("suspended");

    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    media.matches = true;
    listeners.forEach((listener) => listener());
    expect(budgets[budgets.length - 1]).toBe("efficient");
    stop();
    expect(listeners.size).toBe(0);
  });

  it("uses a balanced budget for deliberately reduced effects and avoids duplicate notifications", () => {
    const onBudget = vi.fn();
    const stop = startEngineGovernor({
      doc: document,
      performance: false,
      motionIntensity: "reduced",
      media: { matches: false, addEventListener() {}, removeEventListener() {} },
      onBudget,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(onBudget).toHaveBeenCalledOnce();
    expect(onBudget).toHaveBeenCalledWith("balanced");
    stop();

    const efficient = vi.fn();
    startEngineGovernor({
      doc: document,
      performance: true,
      motionIntensity: "full",
      media: { matches: false, addEventListener() {}, removeEventListener() {} },
      onBudget: efficient,
    })();
    expect(efficient).toHaveBeenCalledWith("efficient");
  });
});
