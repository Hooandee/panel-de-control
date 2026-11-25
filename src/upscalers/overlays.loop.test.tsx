// @vitest-environment happy-dom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: { addGlobalComponent: () => {}, removeGlobalComponent: () => {} }, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }), translate: (key: string) => key }));
import { CoverBadges, coverScan, publishOverview, writeCoverBadges } from "./overlays";

const overview = {
  builds: [{ id: "fsr-4.1.2-beta", engine: "optiscaler", family: "fsr", version: "4.1.2", models: ["lite"] }],
  installs: { "1245620": { build: "fsr-4.1.2-beta", status: "installed", options: { model: "lite" } } },
} as any;

const rect = (width: number, height: number) => () => ({ width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0, toJSON() {} }) as DOMRect;

afterEach(() => { cleanup(); document.body.innerHTML = ""; });

// Loop paints its shelf in a WebGL canvas; the only <img> covers in the DOM are the hidden fallbacks.
it("reports that a canvas-painted shelf has no cover images to mark instead of staying silent", async () => {
  document.body.innerHTML = `<div id="pdc-loop-home"><canvas width="1280" height="800"></canvas>
    <img src="https://steamloopback.host/assets/1245620/library_capsule.jpg" style="opacity:0;width:200px;height:300px"></div>`;
  const hidden = document.querySelector("img")!;
  hidden.getBoundingClientRect = rect(200, 300);
  hidden.parentElement!.getBoundingClientRect = rect(200, 300);
  publishOverview(overview);
  await act(async () => { render(<CoverBadges />); });
  expect(document.querySelector(".pdc-up-badge")).toBeNull();
  expect(coverScan()).toEqual({ labelled: 1, images: 1, placed: 0, skipped: { hidden: 1 } });
});

it("marks the same game once the cover is a visible image", async () => {
  document.body.innerHTML = `<div class="Focusable"><img src="https://steamloopback.host/assets/1245620/library_capsule.jpg"></div>`;
  const img = document.querySelector("img")!;
  img.getBoundingClientRect = rect(200, 300);
  img.parentElement!.getBoundingClientRect = rect(200, 300);
  publishOverview(overview);
  await act(async () => { render(<CoverBadges />); });
  expect(document.querySelector(".pdc-up-badge")).not.toBeNull();
  expect(coverScan()).toMatchObject({ labelled: 1, images: 1, placed: 1 });
});

it("forgets the last scan when the badges are switched off or the component unmounts", async () => {
  document.body.innerHTML = `<div class="Focusable"><img src="https://steamloopback.host/assets/1245620/library_capsule.jpg"></div>`;
  const img = document.querySelector("img")!;
  img.getBoundingClientRect = rect(200, 300);
  img.parentElement!.getBoundingClientRect = rect(200, 300);
  publishOverview(overview);
  const view = render(<CoverBadges />);
  await act(async () => {});
  expect(coverScan()).not.toBeNull();
  await act(async () => { writeCoverBadges(false); });
  expect(coverScan()).toBeNull();
  await act(async () => { writeCoverBadges(true); });
  expect(coverScan()).not.toBeNull();
  view.unmount();
  expect(coverScan()).toBeNull();
});
