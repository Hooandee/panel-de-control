import { describe, expect, it } from "vitest";
import { getUpdaterStrings } from "./strings";

describe("Italian updater strings", () => {
  it("returns the complete Italian updater copy", () => {
    expect(getUpdaterStrings("it")).toEqual({
      panel: {
        version: "Versione",
        latest: "(più recente)",
        newPrefix: "disponibile",
        checking: "verifica in corso…",
        check: "Cerca aggiornamenti",
        update: "Scopri le novità e installa",
        error: "Verifica non riuscita. Controlla la connessione.",
      },
      modal: {
        title: "Novità",
        noNotes: "Nessuna nota per questa versione.",
        install: "Installa l'aggiornamento",
        installing: "Installazione in corso…",
        installed: "Aggiornamento installato.",
        restartNote: "Riavvia Decky per applicare l'aggiornamento.",
        restart: "Riavvia Decky",
        failed: "Installazione non riuscita. Riprova.",
      },
      availableTitle: "Aggiornamento disponibile",
    });
  });
});
