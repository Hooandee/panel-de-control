// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { startBloomStage } from "./bloomStage";

describe("startBloomStage", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.documentElement.style.cssText = "";
  });

  it("mounts a non-interactive two-layer stage and crossfades focused artwork", () => {
    const stage = startBloomStage(document);
    const host = document.getElementById("pdc-obsidian-bloom-stage");
    const layers = [...document.querySelectorAll<HTMLElement>("[data-pdc-bloom-layer]")];

    expect(host?.getAttribute("aria-hidden")).toBe("true");
    expect(host?.querySelector("[tabindex]")).toBeNull();
    expect(layers).toHaveLength(2);

    stage.update("https://cdn.example/one.jpg", new DOMRect(100, 50, 200, 300));
    expect(layers.filter((layer) => layer.dataset.pdcBloomActive === "true")).toHaveLength(1);
    expect(layers.some((layer) => layer.style.backgroundImage.includes("one.jpg"))).toBe(true);
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-focus-x")).toBe("200px");
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-focus-y")).toBe("200px");

    stage.update("https://cdn.example/two.jpg", new DOMRect(300, 100, 100, 100));
    expect(layers.filter((layer) => layer.dataset.pdcBloomActive === "true")).toHaveLength(1);
    expect(layers.every((layer) => layer.style.backgroundImage.length > 0)).toBe(true);
    expect(layers.find((layer) => layer.dataset.pdcBloomActive === "true")?.style.backgroundImage).toContain("two.jpg");

    stage.dispose();
    expect(document.getElementById("pdc-obsidian-bloom-stage")).toBeNull();
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-focus-x")).toBe("");
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-focus-y")).toBe("");
  });

  it("updates the spotlight without decoding the same artwork into the other layer", () => {
    const stage = startBloomStage(document);
    const artwork = "https://cdn.example/same.jpg";
    stage.update(artwork, new DOMRect(0, 0, 100, 100));
    stage.update(artwork, new DOMRect(400, 200, 100, 100));

    const layers = [...document.querySelectorAll<HTMLElement>("[data-pdc-bloom-layer]")];
    expect(layers.filter((layer) => layer.style.backgroundImage.includes("same.jpg"))).toHaveLength(1);
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-focus-x")).toBe("450px");

    stage.dispose();
  });
});
