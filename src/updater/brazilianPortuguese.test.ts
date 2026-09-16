import { describe, expect, it } from "vitest";

import { getUpdaterStrings } from "./strings";

describe("Brazilian Portuguese updater copy", () => {
  it("returns natural Brazilian copy for every updater surface", () => {
    expect(getUpdaterStrings("pt-BR")).toEqual({
      panel: {
        version: "Versão",
        latest: "(mais recente)",
        newPrefix: "nova",
        checking: "verificando…",
        check: "Verificar atualizações",
        update: "Ver novidades e instalar",
        error: "Não foi possível verificar. Confira sua conexão.",
      },
      modal: {
        title: "Novidades",
        noNotes: "Não há notas para esta versão.",
        install: "Instalar atualização",
        installing: "Instalando…",
        installed: "Atualização instalada.",
        restartNote: "Reinicie o Decky para aplicar a atualização.",
        restart: "Reiniciar o Decky",
        failed: "Não foi possível instalar. Tente novamente.",
      },
      availableTitle: "Atualização disponível",
    });
  });
});
