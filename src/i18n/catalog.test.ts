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
const CATALOGS = i18n.SUPPORTED_LANGUAGES.map(
  (lang) => [lang, DICTS[lang]] as const,
);

function italianCatalog(): Record<string, string> {
  return DICTS.it;
}

function germanCatalog(): Record<string, string> {
  return DICTS.de;
}

function placeholders(value: string): string[] {
  return [...(value.match(PLACEHOLDER) ?? [])].sort();
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("Every supported translation catalog", () => {
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

  it("keeps reviewed wording natural in every language", () => {
    expect(DICTS).toMatchObject({
      es: {
        "hud.metric.gpu": "Carga de GPU",
        "hud.metric.gpu_junction_temp": "Punto caliente de GPU",
        "hud.metric.battery_time": "Autonomía",
        "hud.metric.pdc_bat_health": "Salud de la batería",
      },
      en: {
        "display.oled.desc": "Gives your screen a more vibrant, deeper OLED-like look. It changes only the color rendering, not the panel itself.",
        "fans.experimental.resetFail": "Couldn't restart the fan control. Reboot the device if the problem persists.",
        "settings.qamboost.desc": "Raises TDP while the quick access menu is open so it stays responsive. The displayed value applies only while the menu is open. It is adjusted again in game.",
      },
      it: {
        "app.title": "Pannello di controllo",
        "hud.metric.gpu_junction_temp": "Temperatura giunzione GPU",
        "hud.metric.battery_time": "Autonomia batteria",
      },
      de: {
        "app.title": "Kontrollzentrum",
        "params.pill.makoRun.help": "Erzeugt mit Mako Zwischenbilder für flüssigere Bewegungen. Das Skript ~/.local/bin/mako-run muss ausführbar sein.",
        "hud.metric.io_read": "E/A-Lesezugriffe",
        "hud.elements.hint": "Ändere die Reihenfolge mit den Pfeilen. Elemente mit einem Pfeilsymbol haben eigene Einstellungen.",
        "mandos.modules.unavailable": "HHD stellt die erforderliche Schnittstelle nicht bereit. Es wird kein Befehl gesendet.",
        "mandos.modules.confirm.desc": "Halte das Gerät fest und achte darauf, dass die Module Platz haben. Kann HHD die Stromversorgung der Controller nicht direkt abschalten, wird das Gerät möglicherweise in den Standby versetzt, um das Auswerfen abzuschließen.",
        "settings.desktop.desc": "Aktiviert getrennte Regler für CPU, dedizierte GPU und Lüfter auf diesem Linux-PC. Der Modus startet mit „Frei“ und ändert nichts, bis du einen anderen Modus auswählst.",
        "settings.experimentalTdp.confirm.desc": "Damit sind am Netzteil bis zu {max} W möglich und somit mehr als die von GPD angegebenen {safe} W. Behalte die Temperaturen im Blick und deaktiviere die Option, wenn das Gerät sie nicht unter Kontrolle halten kann. Auto-TDP und Voreinstellungen bleiben auf {safe} W begrenzt.",
        "desktop.power.available": "GPU-Leistungslimit",
        "desktop.cpu.draw": "CPU-Leistungsaufnahme",
        "desktop.power.partial": "Es werden nur Regler angezeigt, deren Lese- und Schreibzugriffe das System bestätigt.",
        "desktop.fan.auto.note": "„Automatisch“ gibt diesen Lüfter an die zuvor zuständige Steuerung oder die Firmware zurück.",
        "desktop.fan.firmwareOnly": "Diese Firmware lehnt den manuellen Modus für den GPU-Lüfter ab. Er wird weiterhin überwacht und bleibt automatisch geregelt.",
        "tdp.conflict.powerstation.disablePdc": "TDP im Kontrollzentrum deaktivieren",
      },
    });
  });
});

describe("Italian catalog", () => {
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

  it("warns that AYANEO module ejection may suspend the device", () => {
    expect(DICTS.es["mandos.modules.confirm.desc"]).toContain("suspender");
    expect(DICTS.en["mandos.modules.confirm.desc"]).toContain("suspend");
    expect(DICTS.it["mandos.modules.confirm.desc"]).toContain("sospendersi");
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

  it("distinguishes battery health from charge and capacity", () => {
    expect(italianCatalog()).toMatchObject({
      "hud.metric.pdc_bat_health": "Salute batteria",
      "system.battery.health": "Stato di salute",
      "system.battery.healthGroup": "Stato di salute della batteria",
      "system.battery.capacity": "Capacità",
      "system.battery.limit": "Limite di carica",
    });
  });
});

describe("German catalog", () => {
  it("keeps established technical and product terms", () => {
    const values = Object.values(germanCatalog());
    for (const term of [
      "TDP", "Auto-TDP", "FPS", "CPU", "GPU", "HDR", "RGB", "FSR", "XeSS",
      "RDNA", "Proton", "SteamOS", "Decky", "MangoHud", "GameMode", "PowerStation",
      "SimpleDeckyTDP", "Colores",
    ]) {
      expect(values.some((value) => value.includes(term)), term).toBe(true);
    }
  });

  it("uses natural German product and safety copy", () => {
    expect(germanCatalog()).toMatchObject({
      "app.title": "Kontrollzentrum",
      "lang.german": "Deutsch",
      "display.oled.desc": "Lässt die Farben deines Bildschirms lebendiger und tiefer wirken, ähnlich wie bei einem OLED-Display. Das Display selbst wird nicht verändert, nur die Farbdarstellung.",
      "settings.cooler": "Externe Kühlung angeschlossen",
      "settings.cooler.desc": "Aktiviere diese Option nur, wenn das externe Kühlsystem oder der externe Akku angeschlossen ist. Dadurch steigt das TDP-Limit auf bis zu {max} W. Ohne externe Kühlung kann das Gerät überhitzen.",
    });
  });

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

  it("persists German when its localized selector button is pressed", () => {
    render(
      createElement(
        i18n.I18nProvider,
        null,
        createElement(LanguageToggle),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Alemán" }));

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("de");
  });
});
