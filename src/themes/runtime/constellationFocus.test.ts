// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { startConstellationFocus } from "./constellationFocus";

function grid(size = 6): HTMLElement[] {
  document.body.innerHTML = `<main id="Main"><div role="grid">${Array.from(
    { length: size },
    (_, index) => `<div role="gridcell" data-index="${index}"><button>${index}</button></div>`,
  ).join("")}</div></main>`;
  return [...document.querySelectorAll<HTMLElement>('[role="gridcell"]')];
}

describe("startConstellationFocus", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("marks a bounded constellation around the focused card and clears stale nodes", () => {
    const cards = grid();
    const focus = startConstellationFocus("constellation");

    focus.moveTo(cards[2]);
    expect(cards.map((card) => card.getAttribute("data-pdc-obsidian-distance")))
      .toEqual(["-2", "-1", "0", "1", "2", null]);

    focus.moveTo(cards[4]);
    expect(cards.map((card) => card.getAttribute("data-pdc-obsidian-distance")))
      .toEqual([null, null, "-2", "-1", "0", "1"]);

    focus.dispose();
    expect(cards.every((card) => !card.hasAttribute("data-pdc-obsidian-distance"))).toBe(true);
  });

  it("limits orbit to immediate peers and direct mode to the focused card", () => {
    const cards = grid(5);
    const orbit = startConstellationFocus("orbit");
    orbit.moveTo(cards[2]);
    expect(cards.map((card) => card.getAttribute("data-pdc-obsidian-distance")))
      .toEqual([null, "-1", "0", "1", null]);
    orbit.dispose();

    const direct = startConstellationFocus("direct");
    direct.moveTo(cards[2]);
    expect(cards.map((card) => card.getAttribute("data-pdc-obsidian-distance")))
      .toEqual([null, null, "0", null, null]);
    direct.dispose();
  });
});
