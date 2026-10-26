// PS5 light presets are firmware payloads named by the kernel (they differ between
// kernels), so the label and preview are built from the words of each name.
export type LightColor = "blue" | "white" | "orange" | "pink" | "purple" | "salmon" | "violet";
export type LightStyle = "dim" | "bright" | "soft" | "warm" | "cool" | "breathe" | "pulse" | "fast" | "anim" | "fade" | "sunrise";

const COLOR_WORDS: Record<string, LightColor> = {
  blue: "blue", richblue: "blue", white: "white", orange: "orange", pink: "pink",
  purple: "purple", purplish: "purple", salmon: "salmon", violet: "violet",
};
const STYLE_WORDS: Record<string, LightStyle> = {
  dim: "dim", bright: "bright", rich: "bright", soft: "soft", warm: "warm", cool: "cool",
  breathe: "breathe", pulse: "pulse", fast: "fast", anim: "anim", sunrise: "sunrise",
};

export const SWATCH: Record<LightColor, string> = {
  blue: "#3f7bff", white: "#eef1f6", orange: "#ff8a2b", pink: "#ff6fae",
  purple: "#9a5cff", salmon: "#ff8e78", violet: "#b56cff",
};

export interface LightLook {
  off: boolean;
  colors: LightColor[];
  styles: LightStyle[];
}

export function describePreset(id: string): LightLook {
  const words = id.split("_");
  const colors: LightColor[] = [];
  const styles: LightStyle[] = [];
  for (const word of words) {
    const color = COLOR_WORDS[word];
    const style = STYLE_WORDS[word];
    if (color && !colors.includes(color)) colors.push(color);
    if (style && !styles.includes(style)) styles.push(style);
  }
  if (words.includes("to")) styles.push("fade");
  if (styles.includes("sunrise") && colors.length === 0) colors.push("orange", "pink");
  return { off: id === "off", colors: colors.length ? colors : ["white"], styles };
}

export function presetLabel(id: string, t: (key: string, vars?: Record<string, string | number>) => string): string {
  const look = describePreset(id);
  if (look.off) return t("console.light.off");
  if (look.styles.includes("sunrise")) return t("console.light.style.sunrise");
  const names = look.colors.map((color) => t(`console.light.color.${color}`));
  const joined = names.length > 1
    ? t("console.light.and", { a: names.slice(0, -1).join(", "), b: names[names.length - 1] })
    : names[0];
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

export function presetDetail(id: string, t: (key: string) => string): string {
  return describePreset(id).styles
    .filter((style) => style !== "sunrise")
    .map((style) => t(`console.light.style.${style}`))
    .join(" · ");
}

export function swatchBackground(id: string): string {
  const look = describePreset(id);
  if (look.off) return "transparent";
  const stops = look.colors.map((color) => SWATCH[color]);
  return stops.length === 1 ? stops[0] : `linear-gradient(135deg, ${stops.join(", ")})`;
}
