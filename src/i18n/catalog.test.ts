// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", async () => {
  const { createElement } = await import("react");
  return {
    Dropdown: ({
      rgOptions,
      selectedOption,
      onChange,
      menuLabel,
    }: {
      rgOptions: Array<{ data: string; label: ReactNode }>;
      selectedOption: string;
      onChange?: (option: { data: string; label: ReactNode }) => void;
      menuLabel?: string;
    }) => createElement(
      "select",
      {
        "aria-label": menuLabel,
        value: selectedOption,
        onChange: (event: { target: { value: string } }) => {
          const option = rgOptions.find(({ data }) => data === event.target.value);
          if (option) onChange?.(option);
        },
      },
      rgOptions.map(({ data, label }) => createElement("option", { key: data, value: data }, label)),
    ),
  };
});

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

import { LanguageSelector } from "../components/LanguageSelector";
import * as i18n from "./index";

const DICTS = i18n.DICTS;
const STORAGE_KEY = "panel-de-control-lang";
const PLACEHOLDER = /\{\w+\}/g;
const CATALOGS = i18n.SUPPORTED_LANGUAGES.map(
  (lang) => [lang, DICTS[lang]] as const,
);

function placeholders(value: string): string[] {
  return [...(value.match(PLACEHOLDER) ?? [])].sort();
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("Every supported translation catalog", () => {
  it.each(CATALOGS)("%s includes learned starting watts and FPS without dead reason copy", (_lang, catalog) => {
    expect(placeholders(catalog["tdp.auto.learned_start"])).toEqual(["{fps}", "{watts}"]);
    expect(catalog["tdp.auto.status.above_target"]).toBeUndefined();
  });

  it.each(CATALOGS)("%s has exactly the Spanish keys", (_lang, catalog) => {
    expect(Object.keys(catalog).sort()).toEqual(Object.keys(DICTS.es).sort());
  });

  it.each(CATALOGS)("%s preserves every interpolation placeholder", (_lang, catalog) => {
    for (const key of Object.keys(DICTS.es)) {
      expect(placeholders(catalog[key] ?? ""), key).toEqual(placeholders(DICTS.es[key]));
    }
  });

  it.each(CATALOGS)("%s avoids em dashes in interface copy", (_lang, catalog) => {
    expect(Object.values(catalog).some((value) => value.includes("—"))).toBe(false);
  });

  it("keeps language autonyms out of the translation catalogs", () => {
    expect(Object.keys(DICTS.es).some((key) => key.startsWith("lang."))).toBe(false);
  });
});

describe("Italian catalog", () => {

  it("accepts a persisted Italian selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "it");

    expect(i18n.translate("app.title")).toBe("Pannello di controllo");
  });

  it("formats reviewed count labels without fixed singular or plural forms", () => {
    window.localStorage.setItem(STORAGE_KEY, "it");

    expect(i18n.translate("params.activeCount", { n: 1 })).toBe("Attivi: 1");
    expect(i18n.translate("params.activeCount", { n: 2 })).toBe("Attivi: 2");
    expect(i18n.translate("gameProfiles.buttons", { n: 1 })).toBe("Pulsanti: 1");
    expect(i18n.translate("gameProfiles.buttons", { n: 2 })).toBe("Pulsanti: 2");
  });
});

describe("German catalog", () => {

  it("formats profile counts without an incorrect fixed plural construction", () => {
    window.localStorage.setItem(STORAGE_KEY, "de");

    expect(i18n.translate("gameProfiles.cores", { n: 1 })).toBe("Kerne: 1");
    expect(i18n.translate("gameProfiles.cores", { n: 2 })).toBe("Kerne: 2");
    expect(i18n.translate("gameProfiles.buttons", { n: 1 })).toBe("Tasten: 1");
    expect(i18n.translate("gameProfiles.buttons", { n: 2 })).toBe("Tasten: 2");
  });

  it("accepts a persisted German selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "de");

    expect(i18n.translate("app.title")).toBe("Kontrollzentrum");
  });
});

describe("Brazilian Portuguese catalog", () => {

  it("accepts a persisted Brazilian Portuguese selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "pt-BR");

    expect(i18n.translate("app.title")).toBe("Painel de Controle");
  });
});

describe("French catalog", () => {

  it("formats profile counts without a fixed plural", () => {
    window.localStorage.setItem(STORAGE_KEY, "fr");

    expect(i18n.translate("gameProfiles.cores", { n: 1 })).toBe("Cœurs\u00a0: 1");
    expect(i18n.translate("gameProfiles.buttons", { n: 2 })).toBe("Boutons\u00a0: 2");
    expect(i18n.translate("params.activeCount", { n: 1 })).toBe("Actifs\u00a0: 1");
  });

  it("accepts a persisted French selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "fr");

    expect(i18n.translate("app.title")).toBe("Centre de contrôle");
  });
});

describe("LanguageSelector", () => {
  it("notifies separate roots when the language changes", () => {
    const listener = vi.fn();
    const unsubscribe = i18n.subscribeLanguage(listener);
    render(createElement(i18n.I18nProvider, null, createElement(LanguageSelector)));

    fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), {
      target: { value: "pt-BR" },
    });

    expect(listener).toHaveBeenCalled();
    expect(i18n.getCurrentLanguage()).toBe("pt-BR");
    unsubscribe();
  });
  it("persists Italian when selected", () => {
    render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageSelector),
      ),
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), {
      target: { value: "it" },
    });

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("it");
  });

  it("persists German when selected", () => {
    render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageSelector),
      ),
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), {
      target: { value: "de" },
    });

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("de");
  });

  it("uses one compact dropdown and persists Brazilian Portuguese", () => {
    const { container } = render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageSelector),
      ),
    );

    const selector = screen.getByRole("combobox", { name: "Idioma" });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    const flags = [...container.querySelectorAll<HTMLImageElement>("[data-language-flag]")];
    expect(flags).toHaveLength(6);
    expect(flags.every((flag) => flag.tagName === "IMG")).toBe(true);
    expect(flags.every((flag) => flag.src.startsWith("data:image/svg+xml,"))).toBe(true);
    expect([...selector.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "Español",
      "English",
      "Italiano",
      "Deutsch",
      "Português (Brasil)",
      "Français",
    ]);
    fireEvent.change(selector, { target: { value: "pt-BR" } });

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("pt-BR");
  });

  it("persists French when selected", () => {
    render(createElement(i18n.I18nProvider, null, createElement(LanguageSelector)));

    fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), {
      target: { value: "fr" },
    });

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("fr");
  });
});
