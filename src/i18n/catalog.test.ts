// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", async () => {
  const { createElement } = await import("react");
  return {
    Focusable: ({
      children,
      onActivate: _onActivate,
      onClick,
      ...props
    }: {
      children?: ReactNode;
      onActivate?: () => void;
      onClick?: () => void;
      [key: string]: unknown;
    }) => {
      const interactive = Boolean(onClick || _onActivate);
      return createElement(
        interactive ? "button" : "div",
        { ...props, ...(interactive ? { type: "button" } : {}), onClick },
        children,
      );
    },
  };
});

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

import { LanguageToggle } from "../components/LanguageToggle";
import * as i18n from "./index";

const DICTS = i18n.DICTS;
const STORAGE_KEY = "panel-de-control-lang";
const PLACEHOLDER = /\{\w+\}/g;

function italianCatalog(): Record<string, string> {
  return DICTS.it;
}

function placeholders(value: string): string[] {
  return [...(value.match(PLACEHOLDER) ?? [])].sort();
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("Italian catalog", () => {
  it("has exactly the same keys as the Spanish catalog", () => {
    const italian = italianCatalog();

    expect(Object.keys(italian).sort()).toEqual(Object.keys(DICTS.es).sort());
  });

  it("preserves every interpolation placeholder", () => {
    const italian = italianCatalog();
    const spanish = DICTS.es;

    for (const key of Object.keys(spanish)) {
      expect(placeholders(italian[key] ?? ""), key).toEqual(placeholders(spanish[key]));
    }
  });

  it("does not use em dashes", () => {
    expect(Object.values(italianCatalog()).some((value) => value.includes("—"))).toBe(false);
  });

  it("keeps established technical and product terms", () => {
    const values = Object.values(italianCatalog());
    const terms = [
      "TDP",
      "Auto-TDP",
      "FPS",
      "CPU",
      "GPU",
      "HDR",
      "RGB",
      "FSR",
      "XeSS",
      "RDNA",
      "Proton",
      "SteamOS",
      "Decky",
      "MangoHud",
      "GameMode",
      "PowerStation",
      "SimpleDeckyTDP",
      "Colores",
    ];

    for (const term of terms) {
      expect(values.some((value) => value.includes(term)), term).toBe(true);
    }
  });

  it("uses the Italian product title and an Italian Auto-TDP label", () => {
    const italian = italianCatalog();

    expect(italian["app.title"]).toBe("Pannello di controllo");
    expect(italian["tdp.auto.title"]).toContain("TDP");
    expect(italian["lang.italian"]).toBe("Italiano");
  });

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

  it("uses the reviewed Italian hardware-control labels", () => {
    expect(italianCatalog()).toMatchObject({
      "gpu.clock.manual": "Imposta la frequenza GPU",
      "settings.tdpcontrol": "Controllo del TDP",
      "settings.cooler": "Sistema di raffreddamento esterno collegato",
      "settings.cooler.desc": "Attivalo solo se hai collegato il sistema di raffreddamento esterno o la batteria esterna: aumenta il limite TDP fino a {max} W. Non attivarlo senza il sistema di raffreddamento esterno, perché il dispositivo potrebbe surriscaldarsi.",
    });
  });

  it("uses consistent Italian controller and generated-frame terminology", () => {
    expect(italianCatalog()).toMatchObject({
      "hud.metric.frame_count": "Fotogrammi totali",
      "params.pill.lsfg.desc": "Genera fotogrammi aggiuntivi per una maggiore fluidità. Richiede il plugin lsfg-vk.",
      "params.pill.optiscaler.desc": "Sostituisce DLSS con FSR/XeSS e aggiunge la generazione di fotogrammi. Solo Proton-CachyOS.",
      "params.pill.lsfg.help": "Inserisce fotogrammi intermedi con Lossless Scaling per aumentare la fluidità. È ideale per i giochi a 30-40 FPS. Il moltiplicatore si regola nel plugin lsfg-vk.",
      "params.pill.optiscaler.help": "Sostituisce l'upscaling DLSS con FSR/XeSS e aggiunge la generazione di fotogrammi, integrandosi in Proton-CachyOS senza modificare file. Funziona solo con questa versione di Proton.",
      "mandos.mode.hori_steam": "HORI (giroscopio/pulsanti posteriori)",
    });
  });
});

describe("LanguageToggle", () => {
  it("persists Italian when its localized selector button is pressed", () => {
    render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageToggle),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Italiano" }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("it");
  });
});
