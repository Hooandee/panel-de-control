import { describe, expect, it } from "vitest";

import type { CssLoaderPatch, CssLoaderTheme } from "./cssLoaderTypes";
import {
  planSectionHandoff,
  planSectionRestore,
  sectionKeyOf,
  type SectionHandoffs,
} from "./sectionOwnership";

function patch(name: string, value: "Yes" | "No"): CssLoaderPatch {
  return { name, defaultValue: "Yes", value, options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" };
}

function theme(name: string, enabled: boolean, patches: CssLoaderPatch[]): CssLoaderTheme {
  return { id: name, name, displayName: name, version: "1.0.0", author: "Hooandee", enabled, patches };
}

const HOOANDEE = new Set(["Hooandee Gallery", "Hooandee Luminous Atlas"]);

describe("sectionKeyOf", () => {
  it("maps the section toggles of both Hooandee themes onto shared surfaces", () => {
    expect(sectionKeyOf("Estilizar Inicio")).toBe("home");
    expect(sectionKeyOf("Estilizar Biblioteca y parrilla")).toBe("library");
    expect(sectionKeyOf("Estilizar Biblioteca")).toBe("library");
    expect(sectionKeyOf("Estilizar detalles del juego")).toBe("details");
    expect(sectionKeyOf("Estilizar multimedia y logros")).toBe("achievements");
    expect(sectionKeyOf("Estilizar logros")).toBe("achievements");
    expect(sectionKeyOf("Estilizar menús y barras")).toBe("menu");
    expect(sectionKeyOf("Estilizar menú de Steam")).toBe("menu");
    expect(sectionKeyOf("Estilizar QAM y Decky")).toBe("qam");
    expect(sectionKeyOf("Estilizar Panel de Control")).toBe("panel");
    expect(sectionKeyOf("Estilizar configurador de mando")).toBe("controller");
    expect(sectionKeyOf("Mostrar noticias de Inicio")).toBeNull();
    expect(sectionKeyOf("Estilizar algo nuevo")).toBeNull();
  });
});

describe("planSectionHandoff", () => {
  const gallery = theme("Hooandee Gallery", true, [patch("Estilizar Inicio", "Yes"), patch("Estilizar Ajustes", "Yes")]);
  const atlas = theme("Hooandee Luminous Atlas", true, [patch("Estilizar Inicio", "Yes"), patch("Estilizar Ajustes", "No")]);
  const thirdParty = theme("Someone Else", true, [patch("Estilizar Inicio", "Yes")]);

  it("switches the overlapping sections off in the other active Hooandee theme", () => {
    expect(planSectionHandoff([gallery, atlas, thirdParty], "Hooandee Luminous Atlas", HOOANDEE)).toEqual([
      { themeName: "Hooandee Gallery", patchName: "Estilizar Inicio" },
    ]);
  });

  it("limits the handoff to one section when a single toggle was turned on", () => {
    const both = theme("Hooandee Luminous Atlas", true, [patch("Estilizar Inicio", "Yes"), patch("Estilizar Ajustes", "Yes")]);
    expect(planSectionHandoff([gallery, both], "Hooandee Luminous Atlas", HOOANDEE, "Estilizar Ajustes")).toEqual([
      { themeName: "Hooandee Gallery", patchName: "Estilizar Ajustes" },
    ]);
  });

  it("never touches disabled or third-party themes", () => {
    const idle = theme("Hooandee Gallery", false, [patch("Estilizar Inicio", "Yes")]);
    expect(planSectionHandoff([idle, atlas, thirdParty], "Hooandee Luminous Atlas", HOOANDEE)).toEqual([]);
    expect(planSectionHandoff([gallery, thirdParty], "Someone Else", HOOANDEE)).toEqual([]);
  });
});

describe("planSectionRestore", () => {
  it("gives back only the sections handed to the theme that is leaving", () => {
    const gallery = theme("Hooandee Gallery", true, [patch("Estilizar Inicio", "No"), patch("Estilizar Ajustes", "No")]);
    const handoffs: SectionHandoffs = {
      "Hooandee Gallery\u0000Estilizar Inicio": "Hooandee Luminous Atlas",
      "Hooandee Gallery\u0000Estilizar Ajustes": "Hooandee Other",
    };

    expect(planSectionRestore([gallery], handoffs, "Hooandee Luminous Atlas")).toEqual([
      { themeName: "Hooandee Gallery", patchName: "Estilizar Inicio" },
    ]);
  });

  it("skips sections the user already changed or themes that are gone", () => {
    const gallery = theme("Hooandee Gallery", true, [patch("Estilizar Inicio", "Yes")]);
    const handoffs: SectionHandoffs = {
      "Hooandee Gallery\u0000Estilizar Inicio": "Hooandee Luminous Atlas",
      "Hooandee Missing\u0000Estilizar Inicio": "Hooandee Luminous Atlas",
    };

    expect(planSectionRestore([gallery], handoffs, "Hooandee Luminous Atlas")).toEqual([]);
  });
});
