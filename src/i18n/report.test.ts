import { describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  hydratePrefs: vi.fn(async () => {}),
  onPrefsHealed: vi.fn(() => () => {}),
  prefsHydrated: vi.fn(() => false),
  readString: vi.fn(() => null),
  writeString: vi.fn(),
}));

import { translateForLang } from "./index";

describe("report translations", () => {
  it.each([
    ["es", "Temas"],
    ["en", "Themes"],
    ["it", "Temi"],
    ["pt-BR", "Temas"],
  ] as const)("translates the themes category in %s", (lang, expected) => {
    expect(translateForLang(lang, "report.cat.themes")).toBe(expected);
  });

  it.each([
    ["es", "TDP automático"],
    ["en", "Automatic TDP"],
    ["it", "TDP automatico"],
    ["de", "Automatische TDP-Steuerung"],
    ["pt-BR", "TDP automático"],
  ] as const)("names AutoTDP independently from manual TDP in %s", (lang, expected) => {
    expect(translateForLang(lang, "report.cat.auto_tdp")).toBe(expected);
  });

  it.each([
    ["es", "Una petición o idea", "Esto no es un fallo."],
    ["en", "A request or idea", "This is not a bug report."],
    ["it", "Una richiesta o un'idea", "Questa non è una segnalazione di errore."],
    ["de", "Einen Wunsch oder eine Idee", "Das ist keine Fehlermeldung."],
    ["pt-BR", "Um pedido ou uma ideia", "Isto não é um relatório de erro."],
  ] as const)("makes feature requests explicit in %s", (lang, label, explanation) => {
    expect(translateForLang(lang, "report.kind.feature")).toBe(label);
    expect(translateForLang(lang, "report.intro.feature")).toContain(explanation);
  });

  it.each([
    ["es", "Cambiar"],
    ["en", "Change"],
    ["it", "Cambia"],
    ["de", "Ändern"],
    ["pt-BR", "Alterar"],
  ] as const)("offers a translated report-type change action in %s", (lang, label) => {
    expect(translateForLang(lang, "report.kind.change")).toBe(label);
  });
});
