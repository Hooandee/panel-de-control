import { describe, expect, it } from "vitest";

import { getUpdaterStrings } from "./strings";

describe("Russian updater copy", () => {
  it("returns natural Russian copy for every updater surface", () => {
    expect(getUpdaterStrings("ru")).toEqual({
      floating: { title: "Доступна новая версия", update: "Обновить", later: "Позже" },
      panel: {
        version: "Версия",
        latest: "(последняя)",
        newPrefix: "новая",
        checking: "проверяем…",
        check: "Проверить обновления",
        update: "Что нового и установить",
        error: "Не удалось проверить. Проверь соединение.",
      },
      modal: {
        title: "Что нового",
        noNotes: "Для этой версии нет заметок.",
        install: "Установить обновление",
        installing: "Устанавливаем…",
        installed: "Обновление установлено.",
        restartNote: "Перезапусти Decky, чтобы применить.",
        restart: "Перезапустить Decky",
        failed: "Не удалось установить. Попробуй ещё раз.",
      },
      availableTitle: "Доступно обновление",
    });
  });
});
