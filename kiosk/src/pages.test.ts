import { describe, expect, it } from "vitest";

import { DEFAULT_KIOSK_BLOCKS, kioskPages } from "./pages";

describe("kioskPages", () => {
  it("falls back to a default page when there are no custom views", () => {
    expect(kioskPages([], "Inicio")).toEqual([{ id: "default", name: "Inicio", blocks: DEFAULT_KIOSK_BLOCKS }]);
  });

  it("shows every custom view with blocks as its own page, in order", () => {
    const views = [
      { id: "a", name: "Juego", icon: "star" as const, blocks: ["tdp"] },
      { id: "b", name: "Vacía", icon: "star" as const, blocks: [] },
      { id: "c", name: "Fans", icon: "star" as const, blocks: ["fanRpm", "temps"] },
    ];
    expect(kioskPages(views, "Inicio").map((page) => page.id)).toEqual(["a", "c"]);
  });
});
