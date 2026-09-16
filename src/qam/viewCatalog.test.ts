import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { LuSlidersVertical } from "react-icons/lu";

import type { SectionDef } from "../sections/types";
import { buildQamViewCatalog, targetForQamToken } from "./viewCatalog";

const Component = () => null;
const icon = vi.fn(() => null);
const sections: SectionDef[] = [
  {
    id: "power",
    labelKey: "nav.power",
    descriptionKey: "nav.power.desc",
    accent: "#287d8c",
    icon,
    Component,
  },
  {
    id: "hud",
    labelKey: "nav.hud",
    descriptionKey: "nav.hud.desc",
    accent: "#3e7e5e",
    icon,
    Component,
  },
  {
    id: "view:v1",
    label: "Mi juego",
    labelKey: "customize.views.namePlaceholder",
    descriptionKey: "customize.views.cardDesc",
    accent: "#586b78",
    icon,
    Component,
  },
];

describe("QAM view catalog", () => {
  it("labels the QAM gateway with the application identity", () => {
    expect(buildQamViewCatalog(sections)[0].labelKey).toBe("app.title");
  });

  it("uses the application glyph for the QAM gateway", () => {
    const home = buildQamViewCatalog(sections)[0];

    expect(renderToStaticMarkup(home.icon(20))).toBe(
      renderToStaticMarkup(createElement(LuSlidersVertical, { size: 20 })),
    );
  });

  it("maps Dashboard destinations to stable QAM tokens", () => {
    expect(buildQamViewCatalog(sections).map(({ token, target }) => ({ token, target })))
      .toEqual([
        { token: "pdc:home", target: { kind: "home" } },
        { token: "pdc:section:power", target: { kind: "section", id: "power" } },
        { token: "pdc:section:hud", target: { kind: "section", id: "hud" } },
        { token: "pdc:view:v1", target: { kind: "section", id: "view:v1" } },
      ]);
  });

  it("rejects malformed and unknown Panel tokens", () => {
    expect(targetForQamToken("native:friends")).toBeNull();
    expect(targetForQamToken("pdc:section:")).toBeNull();
    expect(targetForQamToken("pdc:view:")).toBeNull();
  });
});
