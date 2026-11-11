import { describe, expect, it } from "vitest";

import { parseThemeActions, themeActionText } from "./themeActions";

const RESET_HOME = {
  id: "reset-home",
  label: { es: "Restablecer menú principal", en: "Reset home screen", it: "Ripristina il menu principale" },
  description: { es: "Vuelve a la disposición original.", en: "Back to the original layout." },
  confirm: { es: "¿Restablecer el menú principal?", en: "Reset the home screen?" },
  destructive: true,
};

describe("parseThemeActions", () => {
  it("keeps a well formed declaration", () => {
    expect(parseThemeActions([RESET_HOME])).toEqual([RESET_HOME]);
    expect(parseThemeActions([{ id: "reload", label: { en: "Reload" } }])).toEqual([
      { id: "reload", label: { en: "Reload" }, destructive: false },
    ]);
  });

  it.each([undefined, null, "reset-home", { id: "reset-home" }, 3])("reads %s as no actions", (value) => {
    expect(parseThemeActions(value)).toEqual([]);
  });

  it("keeps only entries with an id and a label, leaving limits to the backend", () => {
    const actions = parseThemeActions([
      { id: "", label: { en: "No id" } },
      { id: "no-label" },
      { id: "blank", label: { en: "" } },
      "reset-home",
      null,
      { id: "good", label: { en: "Good", es: 3 }, confirm: "Sure?", destructive: "yes" },
    ]);
    expect(actions).toEqual([{ id: "good", label: { en: "Good" }, destructive: false }]);
  });
});

describe("themeActionText", () => {
  it("prefers Panel's language, then English, then Spanish, then whatever there is", () => {
    expect(themeActionText({ es: "Hola", en: "Hello", it: "Ciao" }, "it")).toBe("Ciao");
    expect(themeActionText({ es: "Hola", en: "Hello" }, "de")).toBe("Hello");
    expect(themeActionText({ es: "Hola", fr: "Salut" }, "de")).toBe("Hola");
    expect(themeActionText({ fr: "Salut" }, "de")).toBe("Salut");
    expect(themeActionText({ "pt-BR": "Olá" }, "pt-BR")).toBe("Olá");
  });
});
