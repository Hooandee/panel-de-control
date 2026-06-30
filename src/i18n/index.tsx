import { FC, ReactNode, createContext, useCallback, useContext, useMemo, useState } from "react";
import { format, Params } from "./format";

export type Lang = "es" | "en";

const STORAGE_KEY = "panel-de-control-lang";

// Spanish first - we value Spanish-speaking users. English is the fallback.
const es: Record<string, string> = {
  "app.title": "Panel de Control",
  "load.error": "No se pudo cargar el estado del plugin. Vuelve a intentarlo en un momento.",
  "load.retry": "Reintentar",
  "device.detected": "{name}",
  "device.generic.badge": "Genérico",
  "device.generic.hint": "No se reconoció tu dispositivo; usando valores conservadores y seguros.",
  "lang.spanish": "Español",
  "lang.english": "Inglés",
  "nav.power": "Potencia",
  "nav.system": "Sistema",
  "nav.fans": "Ventiladores",
  "nav.settings": "Ajustes",
  "fans.unavailable": "No se detectaron ventiladores en este dispositivo.",
  "fans.fan": "Ventilador {n}",
  "fans.temp.cpu": "Procesador",
  "fans.temp.gpu": "Gráfica",
  "fans.curve.title": "Curva de ventilador",
  "fans.preset.auto": "Auto",
  "fans.preset.silent": "Silencioso",
  "fans.preset.balanced": "Equilibrado",
  "fans.preset.performance": "Rendimiento",
  "fans.preset.custom": "Personalizado",
  "fans.curve.custom.hint": "Arrastra los puntos para ajustar tu curva.",
  "fans.curve.expand": "Editar a pantalla completa",
  "fans.curve.saved": "Guardado",
  "fans.curve.auto.hint": "Controlado por el firmware del dispositivo.",
  "fans.curve.unsupported": "El control de ventilador no está disponible en este dispositivo.",
  "fans.suggest.title": "Sugerido para ti",
  "fans.suggest.band": "Ajustada a {lo}–{hi} °C · {min} min",
  "fans.suggest.dial.quiet": "Silencioso",
  "fans.suggest.dial.cool": "Fresco",
  "fans.suggest.apply": "Aplicar sugerencia",
  "fans.suggest.hint.disabled": "Activa «Aprender de mi uso» en Ajustes para recibir sugerencias.",
  "fans.suggest.hint.too_few": "La sugerencia aparecerá tras ~30 min de juego.",
  "fans.suggest.hint.no_data": "La sugerencia aparecerá tras ~30 min de juego.",
  "fans.suggest.hint.flat": "Necesito ver más variación de temperatura para sugerir una curva.",
  "system.brightness": "Brillo",
  "system.volume": "Volumen",
  "system.unavailable": "No disponible en este dispositivo.",
  "settings.language": "Idioma",
  "settings.telemetry": "Aprender de mi uso",
  "settings.telemetry.desc": "Registra temperatura, ventilador y potencia por juego (solo en este dispositivo) para sugerir curvas y perfiles. Nunca sale del dispositivo.",
  "settings.telemetry.learning": "Necesita varias sesiones de juego para aprender tu patrón antes de poder sugerir.",
  "settings.battmax": "Máximo en batería",
  "settings.battmax.desc": "Permite subir el TDP hasta el máximo del equipo también con batería. Más potencia, pero la batería se agota mucho más rápido.",
  "tdp.unsupported": "El control de TDP no está disponible en este dispositivo.",
  "tdp.scope.global": "Global",
  "tdp.inherit": "Heredando del global",
  "tdp.zone.save": "Reposo",
  "tdp.zone.eco": "Ahorro",
  "tdp.zone.balanced": "Equilibrado",
  "tdp.zone.hot": "Alto",
  "tdp.zone.turbo": "Turbo",
  "tdp.preset.save": "Ahorro",
  "tdp.preset.balanced": "Equilibrado",
  "tdp.preset.turbo": "Turbo",
  "tdp.advanced.title": "Avanzado",
  "tdp.advanced.hint": "Margen extra de potencia para picos.",
  "tdp.advanced.auto": "Auto",
  "tdp.advanced.manual": "Manual",
  "tdp.advanced.reset": "Volver a automático",
  "tdp.level.slow": "Boost lento (SPPT)",
  "tdp.level.fast": "Boost rápido (FPPT)",
  "tdp.auto.title": "Auto‑TDP",
  "tdp.auto.hint": "Ajusta la potencia según la carga real.",
  "tdp.ceiling.battery": "Máximo en batería: {max} W. Conecta el cargador para subir más.",
  "tdp.ceiling.charger": "Máximo del dispositivo: {max} W.",
  "tdp.arc.auto": "AUTO",
  "tdp.arc.gpu": "GPU {pct}%",
};

const en: Record<string, string> = {
  "app.title": "Control Center",
  "load.error": "Couldn't load the plugin state. Please try again in a moment.",
  "load.retry": "Retry",
  "device.detected": "{name}",
  "device.generic.badge": "Generic",
  "device.generic.hint": "Your device wasn't recognized; using conservative, safe values.",
  "lang.spanish": "Spanish",
  "lang.english": "English",
  "nav.power": "Power",
  "nav.system": "System",
  "nav.fans": "Fans",
  "nav.settings": "Settings",
  "fans.unavailable": "No fans detected on this device.",
  "fans.fan": "Fan {n}",
  "fans.temp.cpu": "Processor",
  "fans.temp.gpu": "Graphics",
  "fans.curve.title": "Fan curve",
  "fans.preset.auto": "Auto",
  "fans.preset.silent": "Silent",
  "fans.preset.balanced": "Balanced",
  "fans.preset.performance": "Performance",
  "fans.preset.custom": "Custom",
  "fans.curve.custom.hint": "Drag the points to shape your curve.",
  "fans.curve.expand": "Edit full screen",
  "fans.curve.saved": "Saved",
  "fans.curve.auto.hint": "Controlled by the device firmware.",
  "fans.curve.unsupported": "Fan control isn't available on this device.",
  "fans.suggest.title": "Suggested for you",
  "fans.suggest.band": "Tuned to {lo}–{hi} °C · {min} min",
  "fans.suggest.dial.quiet": "Quieter",
  "fans.suggest.dial.cool": "Cooler",
  "fans.suggest.apply": "Apply suggestion",
  "fans.suggest.hint.disabled": "Turn on \"Learn from my usage\" in Settings to get suggestions.",
  "fans.suggest.hint.too_few": "The suggestion will appear after ~30 min of play.",
  "fans.suggest.hint.no_data": "The suggestion will appear after ~30 min of play.",
  "fans.suggest.hint.flat": "I need to see more temperature variation before suggesting a curve.",
  "system.brightness": "Brightness",
  "system.volume": "Volume",
  "system.unavailable": "Not available on this device.",
  "settings.language": "Language",
  "settings.telemetry": "Learn from my usage",
  "settings.telemetry.desc": "Records temperature, fan and power per game (on this device only) to suggest curves and profiles. Never leaves your device.",
  "settings.telemetry.learning": "Needs a few play sessions to learn your pattern before it can suggest.",
  "settings.battmax": "Max power on battery",
  "settings.battmax.desc": "Allow raising TDP to the device maximum on battery too. More performance, but the battery drains much faster.",
  "tdp.unsupported": "TDP control isn't available on this device.",
  "tdp.scope.global": "Global",
  "tdp.inherit": "Inheriting from global",
  "tdp.zone.save": "Idle",
  "tdp.zone.eco": "Eco",
  "tdp.zone.balanced": "Balanced",
  "tdp.zone.hot": "High",
  "tdp.zone.turbo": "Turbo",
  "tdp.preset.save": "Save",
  "tdp.preset.balanced": "Balanced",
  "tdp.preset.turbo": "Turbo",
  "tdp.advanced.title": "Advanced",
  "tdp.advanced.hint": "Extra power headroom for short spikes.",
  "tdp.advanced.auto": "Auto",
  "tdp.advanced.manual": "Manual",
  "tdp.advanced.reset": "Back to automatic",
  "tdp.level.slow": "Slow boost (SPPT)",
  "tdp.level.fast": "Fast boost (FPPT)",
  "tdp.auto.title": "Auto‑TDP",
  "tdp.auto.hint": "Adjusts power to match real load.",
  "tdp.ceiling.battery": "Battery max: {max} W. Plug in the charger to go higher.",
  "tdp.ceiling.charger": "Device max: {max} W.",
  "tdp.arc.auto": "AUTO",
  "tdp.arc.gpu": "GPU {pct}%",
};

const DICTS: Record<Lang, Record<string, string>> = { es, en };

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "es" || stored === "en") return stored;
  } catch {
    /* localStorage may be unavailable; default below */
  }
  return "es"; // Spanish default
}

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, params?: Params) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export const I18nProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore persistence failure */
    }
  }, []);

  const t = useCallback(
    (key: string, params?: Params) => {
      const dict = DICTS[lang];
      const template = dict[key] ?? en[key] ?? key; // fall back to en, then the key itself
      return format(template, params);
    },
    [lang],
  );

  const value = useMemo<I18nValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (ctx) return ctx;
  // Components rendered in a separate React root (e.g. via showModal) live
  // outside the provider. Rather than throw, degrade to a snapshot of the
  // persisted language — setLang is a no-op there (the modal opens after any
  // language change and can't receive live updates anyway).
  const lang = initialLang();
  return {
    lang,
    setLang: () => {},
    t: (key, params) => format(DICTS[lang][key] ?? en[key] ?? key, params),
  };
}
