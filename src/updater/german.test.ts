import { describe, expect, it } from "vitest";

import { getUpdaterStrings } from "./strings";

describe("German updater copy", () => {
  it("returns natural German copy for every updater surface", () => {
    expect(getUpdaterStrings("de")).toEqual({
      panel: {
        version: "Version",
        latest: "(aktuell)",
        newPrefix: "neu",
        checking: "Suche läuft…",
        check: "Nach Updates suchen",
        update: "Neuigkeiten ansehen und installieren",
        error: "Die Suche ist fehlgeschlagen. Prüfe deine Verbindung.",
      },
      modal: {
        title: "Neuigkeiten",
        noNotes: "Für diese Version gibt es keine Hinweise.",
        install: "Update installieren",
        installing: "Installation läuft…",
        installed: "Update installiert.",
        restartNote: "Starte Decky neu, um das Update anzuwenden.",
        restart: "Decky neu starten",
        failed: "Die Installation ist fehlgeschlagen. Versuche es erneut.",
      },
      availableTitle: "Update verfügbar",
    });
  });
});
