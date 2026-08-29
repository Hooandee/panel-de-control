import type { Lang } from "../i18n";

const ENGLISH: Readonly<Record<string, string>> = {
  "Acento bioluminiscente": "Bioluminescent accent",
  "Densidad de parrilla": "Grid density",
  "Animaciones de parrilla": "Grid animations",
  "Intensidad de movimiento": "Motion intensity",
  "Fondo adaptativo": "Adaptive backdrop",
  "Escena de biblioteca": "Library scene",
  "Escena de parrilla": "Grid scene",
  "Transición al detalle": "Details transition",
  "Estilo de ajustes": "Settings style",
  "Modo de rendimiento": "Performance mode",
  "Dúo": "Duo",
  "Cian": "Cyan",
  "Compacta": "Compact",
  "Cinemática": "Cinematic",
  "Galería": "Gallery",
  "Reducida": "Reduced",
  "Equilibrada": "Balanced",
  "Total": "Full",
  "Apagado": "Off",
  "Sutil": "Subtle",
  "Cinemático": "Cinematic",
  "Inmersivo": "Immersive",
  "Esencial": "Essential",
  "Atmosférica": "Atmospheric",
  "Inmersiva": "Immersive",
  "Directa": "Direct",
  "Órbita": "Orbit",
  "Constelación": "Constellation",
  "Abismo orbital": "Orbital Abyss",
  "Ninguna": "None",
  "Fundido": "Fade",
  "Cristal": "Glass",
  "Cometa": "Comet",
};

const SPANISH: Readonly<Record<string, string>> = {
  Yes: "Sí",
};

export function presentThemePatchText(raw: string, lang: Lang): string {
  return (lang === "en" ? ENGLISH : SPANISH)[raw] ?? raw;
}
