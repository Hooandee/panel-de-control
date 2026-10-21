import { describe, expect, it } from "vitest";

import { getUpdaterStrings } from "./strings";

describe("French updater copy", () => {
  it("returns natural French copy for every updater surface", () => {
    expect(getUpdaterStrings("fr")).toEqual({
      floating: { title: "Nouvelle version disponible", update: "Mettre à jour", later: "Plus tard" },
      panel: {
        version: "Version",
        latest: "(à jour)",
        newPrefix: "nouvelle",
        checking: "recherche…",
        check: "Rechercher des mises à jour",
        update: "Voir les nouveautés et installer",
        error: "La recherche a échoué. Vérifiez votre connexion.",
      },
      modal: {
        title: "Nouveautés",
        noNotes: "Aucune note pour cette version.",
        install: "Installer la mise à jour",
        installing: "Installation…",
        installed: "Mise à jour installée.",
        restartNote: "Redémarrez Decky pour appliquer la mise à jour.",
        restart: "Redémarrer Decky",
        failed: "L'installation a échoué. Réessayez.",
      },
      availableTitle: "Mise à jour disponible",
    });
  });
});
