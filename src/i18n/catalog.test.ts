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

function italianCatalog(): Record<string, string> {
  return DICTS.it;
}

function germanCatalog(): Record<string, string> {
  return DICTS.de;
}

function brazilianPortugueseCatalog(): Record<string, string> {
  return DICTS["pt-BR"];
}

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

  it("provides localized Steam performance status copy", () => {
    expect(DICTS).toMatchObject({
      es: { "steam.performance.title": "Rendimiento de Steam" },
      en: { "steam.performance.title": "Steam performance" },
      it: { "steam.performance.title": "Prestazioni di Steam" },
      de: { "steam.performance.title": "Steam-Leistung" },
      "pt-BR": { "steam.performance.title": "Desempenho do Steam" },
    });
  });

  it("provides dashboard copy in every supported language", () => {
    expect(DICTS).toMatchObject({
      es: {
        "home.title": "Inicio",
        "home.subtitle": "Elige una herramienta",
        "home.tabs": "Vista de pestañas",
        "home.back": "Inicio",
        "home.changeSection": "Cambiar sección",
        "customize.home": "Vista principal",
        "customize.home.desc": "Elige cómo navegar por Panel de Control.",
        "customize.home.dashboard": "Dashboard",
        "customize.home.tabs": "Pestañas",
        "customize.deviceHeader": "Mostrar información del dispositivo",
        "customize.deviceHeader.desc": "Muestra una identificación compacta del dispositivo bajo el título.",
        "customize.views.cardDesc": "Vista personalizada",
        "nav.power.desc": "Rendimiento y consumo del dispositivo.",
        "nav.system.desc": "Controles y estado general del sistema.",
        "nav.display.desc": "Ajustes disponibles de imagen y pantalla.",
        "nav.fans.desc": "Estado térmico y opciones de ventilación.",
        "nav.audio.desc": "Controles disponibles de sonido.",
        "nav.mandos.desc": "Estado y opciones disponibles del mando.",
        "nav.hud.desc": "Información y diseño de la interfaz en juego.",
        "nav.params.desc": "Inicio y compatibilidad de los juegos.",
        "nav.themes.desc": "Apariencia del Panel de Control.",
        "nav.settings.desc": "Personalización, actualizaciones e información.",
      },
      en: {
        "home.title": "Home",
        "home.subtitle": "Choose a tool",
        "home.tabs": "Tab view",
        "home.back": "Home",
        "home.changeSection": "Change section",
        "customize.home": "Main view",
        "customize.home.desc": "Choose how to navigate Control Center.",
        "customize.home.dashboard": "Dashboard",
        "customize.home.tabs": "Tabs",
        "customize.deviceHeader": "Show device information",
        "customize.deviceHeader.desc": "Shows a compact device identifier below the title.",
        "customize.views.cardDesc": "Custom view",
        "nav.power.desc": "Device performance and power use.",
        "nav.system.desc": "General system controls and status.",
        "nav.display.desc": "Available image and display settings.",
        "nav.fans.desc": "Thermal status and available fan options.",
        "nav.audio.desc": "Available sound controls.",
        "nav.mandos.desc": "Controller status and available options.",
        "nav.hud.desc": "In-game overlay information and layout.",
        "nav.params.desc": "Game startup and compatibility.",
        "nav.themes.desc": "Control Center appearance.",
        "nav.settings.desc": "Customization, updates, and information.",
      },
      it: {
        "home.title": "Home",
        "home.subtitle": "Scegli uno strumento",
        "home.tabs": "Vista a schede",
        "home.back": "Home",
        "home.changeSection": "Cambia sezione",
        "customize.home": "Vista principale",
        "customize.home.desc": "Scegli come navigare nel Pannello di controllo.",
        "customize.home.dashboard": "Dashboard",
        "customize.home.tabs": "Schede",
        "customize.deviceHeader": "Mostra informazioni sul dispositivo",
        "customize.deviceHeader.desc": "Mostra un identificatore compatto del dispositivo sotto il titolo.",
        "customize.views.cardDesc": "Vista personalizzata",
        "nav.power.desc": "Prestazioni e consumi del dispositivo.",
        "nav.system.desc": "Controlli e stato generale del sistema.",
        "nav.display.desc": "Impostazioni disponibili per immagine e schermo.",
        "nav.fans.desc": "Stato termico e opzioni di ventilazione.",
        "nav.audio.desc": "Controlli audio disponibili.",
        "nav.mandos.desc": "Stato e opzioni disponibili del controller.",
        "nav.hud.desc": "Informazioni e disposizione dell'interfaccia in gioco.",
        "nav.params.desc": "Avvio e compatibilità dei giochi.",
        "nav.themes.desc": "Aspetto di Pannello di controllo.",
        "nav.settings.desc": "Personalizzazione, aggiornamenti e informazioni.",
      },
      de: {
        "home.title": "Start",
        "home.subtitle": "Wähle ein Werkzeug",
        "home.tabs": "Tab-Ansicht",
        "home.back": "Start",
        "home.changeSection": "Bereich wechseln",
        "customize.home": "Hauptansicht",
        "customize.home.desc": "Wähle, wie du durch das Kontrollzentrum navigierst.",
        "customize.home.dashboard": "Dashboard",
        "customize.home.tabs": "Tabs",
        "customize.deviceHeader": "Geräteinformationen anzeigen",
        "customize.deviceHeader.desc": "Zeigt eine kompakte Gerätekennung unter dem Titel.",
        "customize.views.cardDesc": "Benutzerdefinierte Ansicht",
        "nav.power.desc": "Leistung und Energieverbrauch des Geräts.",
        "nav.system.desc": "Allgemeine Systemsteuerung und Status.",
        "nav.display.desc": "Verfügbare Bild- und Anzeigeeinstellungen.",
        "nav.fans.desc": "Temperaturstatus und verfügbare Lüfteroptionen.",
        "nav.audio.desc": "Verfügbare Audiosteuerung.",
        "nav.mandos.desc": "Controllerstatus und verfügbare Optionen.",
        "nav.hud.desc": "Informationen und Layout der Spielanzeige.",
        "nav.params.desc": "Spielstart und Kompatibilität.",
        "nav.themes.desc": "Erscheinungsbild des Kontrollzentrums.",
        "nav.settings.desc": "Anpassung, Updates und Informationen.",
      },
    });
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

describe("Brazilian Portuguese catalog", () => {
  it("is a first-class supported language with reviewed Brazilian wording", () => {
    expect(i18n.SUPPORTED_LANGUAGES).toContain("pt-BR");
    expect(brazilianPortugueseCatalog()).toMatchObject({
      "app.title": "Painel de Controle",
      "load.retry": "Tentar novamente",
      "fans.suggest.dial.cool": "Mais frio",
      "cleaner.reason.tool_in_use": "Um jogo está configurado para usar esta versão do Proton. Ela será mantida.",
      "params.caveat.locale": "No SteamOS padrão, talvez não seja possível forçar o idioma.",
      "learning.title": "Aprendendo com {name}",
      "system.rgb.confirm.desc": "Colores será baixado e instalado a partir do GitHub. Continuar?",
      "system.battery.health": "Saúde da bateria",
      "settings.desktop.desc": "Ativa controles separados de CPU, GPU dedicada e ventoinha neste PC Linux. O modo inicial é Livre e nada muda até você selecionar outro modo.",
      "settings.language": "Idioma",
      "tdp.inherit": "Usando a configuração global",
      "tdp.presets.add": "Adicionar predefinição",
      "tdp.conflict.cede": "Passar o controle para o Painel de Controle",
    });
  });

  it("keeps established gaming, hardware and product terms", () => {
    const values = Object.values(brazilianPortugueseCatalog());
    for (const term of [
      "TDP", "Auto-TDP", "FPS", "CPU", "GPU", "HDR", "RGB", "FSR", "XeSS",
      "RDNA", "Proton", "SteamOS", "Decky", "MangoHud", "GameMode", "PowerStation",
      "SimpleDeckyTDP", "Colores",
    ]) {
      expect(values.some((value) => value.includes(term)), term).toBe(true);
    }
    expect(values.some((value) => /\b[Vv]entilador/.test(value))).toBe(false);
  });

  it("avoids reviewed calques and inconsistent Brazilian terms", () => {
    const catalog = Object.values(brazilianPortugueseCatalog()).join("\n");

    for (const rejected of [
      "screenshot",
      "Cache de Shaders",
      "micro-travamentos",
      "paddles",
      "Overlay",
      "engines Source",
      "(offline?)",
      "Parâmetros de lançamento",
      "configurações configuráveis",
      "já seu",
    ]) {
      expect(catalog, rejected).not.toContain(rejected);
    }
  });

  it("accepts a persisted Brazilian Portuguese selection for lookup", () => {
    window.localStorage.setItem(STORAGE_KEY, "pt-BR");

    expect(i18n.translate("app.title")).toBe("Painel de Controle");
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
    expect(flags).toHaveLength(5);
    expect(flags.every((flag) => flag.tagName === "IMG")).toBe(true);
    expect(flags.every((flag) => flag.src.startsWith("data:image/svg+xml,"))).toBe(true);
    expect([...selector.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "Español",
      "English",
      "Italiano",
      "Deutsch",
      "Português (Brasil)",
    ]);
    fireEvent.change(selector, { target: { value: "pt-BR" } });

    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("pt-BR");
  });
});
