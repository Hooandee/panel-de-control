import { describe, expect, it } from "vitest";

import { SUPPORTED_LANGUAGES, type Lang } from "../i18n/languages";
import { getUpdaterStrings } from "./strings";

function updaterValues(lang: Lang): string[] {
  const { panel, modal, availableTitle } = getUpdaterStrings(lang);
  return [...Object.values(panel), ...Object.values(modal), availableTitle];
}

describe("Updater translation content", () => {
  it.each(SUPPORTED_LANGUAGES)("%s avoids em dashes", (lang) => {
    expect(updaterValues(lang).some((value) => value.includes("—"))).toBe(false);
  });

  it("keeps reviewed actions natural in every language", () => {
    expect(getUpdaterStrings("es").panel.update).toBe("Ver novedades e instalar");
    expect(getUpdaterStrings("en").modal.restartNote).toBe("Restart Decky to apply it.");
    expect(getUpdaterStrings("it").panel.check).toBe("Cerca aggiornamenti");
    expect(getUpdaterStrings("de").panel.check).toBe("Nach Updates suchen");
    expect(getUpdaterStrings("pt-BR").panel.check).toBe("Verificar atualizações");
  });
});
